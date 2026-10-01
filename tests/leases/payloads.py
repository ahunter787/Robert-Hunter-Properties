"""POST data for the lease desk, in the inline formset's own vocabulary.

Kept in one place because the management form is easy to get subtly wrong: a
tenant the lease *already has* must be posted as an INITIAL form. Post it as a
new row and Django treats it as an addition, so the database's one-row-per-tenant
rule refuses a save the operator never asked for.
"""

import datetime as dt

from django.utils import timezone

TODAY = timezone.localdate()


def lease_post_data(unit, tenants=(), *, lease=None, **overrides):
    """POST data that recreates ``lease``, plus ``tenants`` as new rows.

    ``unit`` is the unit to post and ``tenants`` are rows to add. Pass ``lease``
    when editing: its existing tenant rows are then posted back as initial forms,
    which is what the edit form in a browser sends.
    """
    initial = list(lease.lease_tenants.all().order_by("pk")) if lease is not None else []
    data = {
        "unit": unit.pk,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + dt.timedelta(days=365)).isoformat(),
        "monthly_rent": "1850.00",
        "deposit": "1850.00",
        "rent_due_day": "1",
        "notes": "",
        "lease_tenants-TOTAL_FORMS": str(len(initial) + len(tenants)),
        "lease_tenants-INITIAL_FORMS": str(len(initial)),
        "lease_tenants-MIN_NUM_FORMS": "0",
        "lease_tenants-MAX_NUM_FORMS": "1000",
    }

    index = 0
    for membership in initial:
        data[f"lease_tenants-{index}-id"] = membership.pk
        data[f"lease_tenants-{index}-lease"] = lease.pk
        data[f"lease_tenants-{index}-tenant"] = membership.tenant_id
        if membership.is_primary:
            data[f"lease_tenants-{index}-is_primary"] = "on"
        index += 1

    for tenant in tenants:
        data[f"lease_tenants-{index}-tenant"] = tenant.pk
        if index == 0:
            # The only row: it has to be the primary contact.
            data[f"lease_tenants-{index}-is_primary"] = "on"
        index += 1

    data.update(overrides)
    return data
