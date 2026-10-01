"""Phase 1 views: sign-in, account self-service, and account administration.

Authorization lives here, not in templates: every view that returns RHP data is
gated by a mixin from :mod:`apps.accounts.permissions` (ADR-003).
"""

import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts import emails
from apps.accounts.forms import (
    InvitationPasswordForm,
    ProfileForm,
    TenantCreateForm,
    TenantRoleForm,
    ThrottledLoginForm,
)
from apps.accounts.models import Role, TenantProfile, User
from apps.accounts.permissions import (
    AdminRequiredMixin,
    ManagerRequiredMixin,
    StaffRequiredMixin,
)
from apps.accounts.throttle import LoginThrottle, client_ip
from apps.accounts.tokens import invitation_token_generator
from apps.leases.models import Lease, LeaseStatus
from apps.properties.models import Property, Unit

logger = logging.getLogger("apps.accounts")


# --- Authentication -------------------------------------------------------


class ThrottledLoginView(LoginView):
    """Sign-in with a failure budget; see docs/security.md for the thresholds."""

    template_name = "account/login.html"
    form_class = ThrottledLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        username = form.cleaned_data.get("username", "")
        LoginThrottle().record_success(username, client_ip(self.request))
        logger.info("login success user=%s", form.get_user().pk)
        return super().form_valid(form)

    def form_invalid(self, form):
        # A throttled attempt is not another credential failure: recording it
        # would extend the lockout every time the user retries.
        if not ThrottledLoginForm.is_throttle_error(form):
            username = self.request.POST.get("username", "")
            LoginThrottle().record_failure(username, client_ip(self.request))
            logger.warning("login failure username=%r", username[:150])
        return super().form_invalid(form)


class PostLoginRedirectView(LoginRequiredMixin, View):
    """Send each role to the area it can actually use."""

    def get(self, request):
        if request.user.is_rhp_staff:
            return redirect("manage:home")
        return redirect("accounts:profile")


# --- Account self-service -------------------------------------------------


class ProfileView(LoginRequiredMixin, View):
    """Tenants edit their contact details; staff see a read-only summary."""

    template_name = "account/profile.html"

    def get(self, request):
        profile = getattr(request.user, "tenant_profile", None)
        form = ProfileForm(instance=profile) if request.user.is_tenant else None
        return render(request, self.template_name, {"form": form, "profile": profile})

    def post(self, request):
        if not request.user.is_tenant:
            raise PermissionDenied("Staff accounts do not hold tenant contact details.")
        profile, _ = TenantProfile.objects.get_or_create(user=request.user)
        form = ProfileForm(request.POST, instance=profile)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "profile": profile})
        form.save()
        logger.info("profile updated user=%s", request.user.pk)
        messages.success(request, "Your contact details were updated.")
        return redirect("accounts:profile")


class InvitationAcceptView(FormView):
    """Accept a tenant invitation: verify the token, set a password, sign in."""

    template_name = "account/invite.html"
    form_class = InvitationPasswordForm

    def dispatch(self, request, uidb64, token, *args, **kwargs):
        self.invited_user = self._resolve_user(uidb64)
        if self.invited_user is None or not invitation_token_generator.check_token(
            self.invited_user, token
        ):
            return render(request, "account/invite_invalid.html", status=400)
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _resolve_user(uidb64: str) -> User | None:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            return User.objects.get(pk=uid)
        except TypeError, ValueError, OverflowError, User.DoesNotExist:
            return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.invited_user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invited_user"] = self.invited_user
        return context

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        logger.info("invitation accepted user=%s", user.pk)
        messages.success(self.request, "Your password is set. Welcome to RHP.")
        return redirect("accounts:home")


# --- Management area: accounts --------------------------------------------


def _invited_accounts():
    """Accounts that were created but have never set a password.

    Django stores an unusable password with a leading ``!`` and has no queryset
    filter for it, so the prefix is used directly (asserted by tests).
    """
    return User.objects.filter(password__startswith="!")  # noqa: S106 - unusable-password prefix


class ManageHomeView(StaffRequiredMixin, TemplateView):
    """Staff landing page, with the counters each role can actually use.

    The portfolio counts come from `apps.properties`. This view aggregates
    another app's public models because it *is* the cross-domain landing page;
    Phase 9 moves dashboards into their own app.
    """

    template_name = "management/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["is_admin"] = user.is_admin_or_above
        context["is_manager"] = user.is_manager_or_above

        if user.is_manager_or_above:
            context["property_active_count"] = Property.objects.active().count()
            context["property_total_count"] = Property.objects.count()
            context["unit_active_count"] = Unit.objects.active().count()
            context["unit_total_count"] = Unit.objects.count()
            context["tenant_active_count"] = User.objects.filter(
                role=Role.TENANT, is_active=True
            ).count()

            # Occupancy comes from the lease definition, never from a stored flag:
            # a unit is occupied while an active lease's term covers today.
            occupied_unit_ids = Lease.objects.current().values("unit_id")
            in_service = Unit.objects.active()
            context["unit_occupied_count"] = in_service.filter(pk__in=occupied_unit_ids).count()
            context["unit_vacant_count"] = in_service.exclude(pk__in=occupied_unit_ids).count()
            context["lease_active_count"] = Lease.objects.active().count()
            context["lease_draft_count"] = Lease.objects.filter(status=LeaseStatus.DRAFT).count()
            context["lease_expiring_count"] = Lease.objects.expiring_within(30).count()

        if user.is_admin_or_above:
            context["tenant_invited_count"] = _invited_accounts().filter(role=Role.TENANT).count()
        return context


class TenantAccountListView(ManagerRequiredMixin, ListView):
    """Tenant list. Managers may read it; only admins may change anything."""

    template_name = "management/account_list.html"
    context_object_name = "accounts"
    paginate_by = 25

    def get_queryset(self):
        queryset = (
            User.objects.filter(role=Role.TENANT)
            .select_related("tenant_profile")
            .order_by("last_name", "first_name", "username")
        )
        search = self.request.GET.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        status = self.request.GET.get("status", "")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        elif status == "invited":
            queryset = _invited_accounts().filter(role=Role.TENANT)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "")
        context["status"] = self.request.GET.get("status", "")
        return context


class TenantAccountCreateView(AdminRequiredMixin, FormView):
    """Admin-created tenant accounts: staff stays in control of who gets access."""

    template_name = "management/account_form.html"
    form_class = TenantCreateForm

    def form_valid(self, form):
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            role=Role.TENANT,
        )
        TenantProfile.objects.create(user=user, phone=form.cleaned_data["phone"])
        delivered = emails.send_invitation(user, self.request.build_absolute_uri("/"))
        logger.info(
            "tenant account created user=%s by=%s emailed=%s",
            user.pk,
            self.request.user.pk,
            delivered,
        )
        if delivered:
            messages.success(self.request, f"Invitation sent to {user.email}.")
        else:
            messages.warning(
                self.request,
                "Account created, but no email was delivered: RHP is using the console "
                "email backend. The invitation link is in the application log.",
            )
        return redirect("manage:account-detail", pk=user.pk)


class TenantAccountDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/account_detail.html"
    context_object_name = "account"

    def get_queryset(self):
        return User.objects.select_related("tenant_profile")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_form"] = TenantRoleForm(instance=self.object)
        context["can_change_roles"] = self.request.user.is_superadmin
        return context


class TenantAccountToggleActiveView(AdminRequiredMixin, View):
    """Deactivate or reactivate. Accounts are never deleted."""

    http_method_names = ["post"]

    def post(self, request, pk):
        account = get_object_or_404(User, pk=pk, role=Role.TENANT)
        account.is_active = not account.is_active
        account.save(update_fields=["is_active"])
        logger.info(
            "account active=%s user=%s by=%s", account.is_active, account.pk, request.user.pk
        )
        state = "reactivated" if account.is_active else "deactivated"
        messages.success(request, f"{account.display_name} was {state}.")
        return redirect("manage:account-detail", pk=account.pk)


class TenantAccountResendInviteView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        account = get_object_or_404(User, pk=pk, role=Role.TENANT)
        if account.has_usable_password():
            messages.warning(
                request,
                f"{account.display_name} has already set a password; "
                "send a password reset instead.",
            )
            return redirect("manage:account-detail", pk=account.pk)
        delivered = emails.send_invitation(account, request.build_absolute_uri("/"))
        if delivered:
            messages.success(request, f"Invitation re-sent to {account.email}.")
        else:
            messages.warning(
                request,
                "No email was delivered: RHP is using the console email backend. "
                "The invitation link is in the application log.",
            )
        return redirect("manage:account-detail", pk=account.pk)


class TenantRoleChangeView(AdminRequiredMixin, View):
    """Role changes are privileged: only a superadmin may perform them."""

    http_method_names = ["post"]

    def post(self, request, pk):
        if not request.user.is_superadmin:
            raise PermissionDenied("Only a superadmin may change roles.")
        account = get_object_or_404(User, pk=pk)
        # Captured before the form is bound: a ModelForm mutates its instance
        # during validation, so reading it afterwards would report the new role.
        previous = account.role
        form = TenantRoleForm(request.POST, instance=account)
        if not form.is_valid():
            messages.error(request, "That role change was not valid.")
            return redirect("manage:account-detail", pk=account.pk)
        account = form.save()
        logger.info(
            "role changed user=%s from=%s to=%s by=%s",
            account.pk,
            previous,
            account.role,
            request.user.pk,
        )
        messages.success(request, f"{account.display_name} is now {account.get_role_display()}.")
        return redirect("manage:account-detail", pk=account.pk)
