from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.accounts.permissions import ManagerRequiredMixin

from . import activity, services


class MetricDetail(ManagerRequiredMixin, View):
    def get(self, request, metric):
        projection = services.project(request.user)
        if metric not in projection["metrics"]:
            raise Http404
        selected = projection["metrics"][metric]
        return render(
            request,
            "dashboard/detail.html",
            {
                "metric": selected,
                "updated_at": projection["updated_at"],
                "page": Paginator(selected.rows, 25).get_page(request.GET.get("page")),
            },
        )


class ActivityBrowser(ManagerRequiredMixin, View):
    def get(self, request):
        form = activity.Filters(request.GET or None, user=request.user)
        rows = activity.visible(request.user)
        invalid = bool(request.GET) and not form.is_valid()
        if request.GET and not invalid:
            rows = activity.filtered(request.user, form.cleaned_data)
        if invalid:
            rows = rows.none()
        page = Paginator(rows, 25).get_page(request.GET.get("page"))
        params = request.GET.copy()
        params.pop("page", None)
        return render(
            request,
            "dashboard/activity.html",
            {
                "form": form,
                "page": page,
                "events": activity.project(page.object_list),
                "filter_query": params.urlencode(),
            },
            status=400 if invalid else 200,
        )
