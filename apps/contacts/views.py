"""The people screen: master data for lease parties, with optional portal logins."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from apps.accounts import emails
from apps.accounts.models import Role, TenantProfile, User
from apps.accounts.permissions import ManagerRequiredMixin
from apps.contacts import services
from apps.contacts.forms import LinkAccountForm, PersonCreateForm, PersonForm
from apps.contacts.models import Person


class PersonListView(ManagerRequiredMixin, ListView):
    template_name = "management/people_list.html"
    context_object_name = "people"
    paginate_by = 50

    def get_queryset(self):
        queryset = Person.objects.all()
        search = self.request.GET.get("q", "").strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
        return queryset.prefetch_related("lease_memberships__lease__unit__property")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search"] = self.request.GET.get("q", "").strip()
        return context


class PersonCreateView(ManagerRequiredMixin, View):
    template_name = "management/person_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": PersonCreateForm()})

    def post(self, request):
        form = PersonCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                person = Person.objects.create(
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                )
                delivered = None
                if form.cleaned_data["give_portal_access"]:
                    user = User.objects.create_user(
                        username=form.cleaned_data["username"],
                        email=form.cleaned_data["email"],
                        first_name=form.cleaned_data["first_name"],
                        last_name=form.cleaned_data["last_name"],
                        role=Role.TENANT,
                    )
                    TenantProfile.objects.create(user=user, phone=form.cleaned_data["phone"])
                    services.link_portal_account(person, user, actor=request.user)
                    delivered = emails.send_invitation(user, request.build_absolute_uri("/"))
            if delivered:
                messages.success(request, f"Invitation sent to {person.email}.")
            elif delivered is False:
                messages.warning(
                    request,
                    "The person was created, but the invitation email was not sent. "
                    "Ask the site administrator to check email delivery.",
                )
            else:
                messages.success(request, f"{person.display_name} was added.")
            return redirect("contacts:person-detail", pk=person.pk)
        return render(request, self.template_name, {"form": form})


class PersonDetailView(ManagerRequiredMixin, DetailView):
    template_name = "management/person_detail.html"
    context_object_name = "person"

    def get_queryset(self):
        return Person.objects.select_related("portal_user").prefetch_related(
            "lease_memberships__lease__unit__property"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PersonForm(instance=self.object)
        link_form = LinkAccountForm(person=self.object)
        context["link_form"] = link_form
        context["link_available"] = link_form.fields["user"].queryset.exists()
        context["memberships"] = self.object.lease_memberships.select_related(
            "lease__unit__property"
        ).order_by("-lease__start_date")
        return context


class PersonUpdateView(ManagerRequiredMixin, View):
    template_name = "management/person_form.html"

    def _person(self, pk):
        return get_object_or_404(Person, pk=pk)

    def get(self, request, pk):
        person = self._person(pk)
        return render(
            request,
            self.template_name,
            {"form": PersonForm(instance=person), "person": person},
        )

    def post(self, request, pk):
        person = self._person(pk)
        form = PersonForm(request.POST, instance=person)
        if form.is_valid():
            form.save()
            messages.success(request, f"{person.display_name} was updated.")
            return redirect("contacts:person-detail", pk=person.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "person": person},
        )


class PersonLinkAccountView(ManagerRequiredMixin, View):
    """Attach an existing tenant account to a person who has none."""

    http_method_names = ["post"]

    def post(self, request, pk):
        person = get_object_or_404(Person.objects.select_related("portal_user"), pk=pk)
        form = LinkAccountForm(request.POST, person=person)
        if not form.is_valid():
            messages.error(request, "Choose an active tenant account that is not linked yet.")
            return redirect("contacts:person-detail", pk=person.pk)
        try:
            services.link_portal_account(person, form.cleaned_data["user"], actor=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"{form.cleaned_data['user'].display_name} can now sign in as "
                f"{person.display_name}.",
            )
        return redirect("contacts:person-detail", pk=person.pk)
