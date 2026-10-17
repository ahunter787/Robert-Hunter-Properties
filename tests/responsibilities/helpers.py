"""Submit the same explicit fields and review tokens as the browser."""

from django.urls import reverse


def payload(response, **changes):
    result = {"baseline": response.context["baseline"]}
    for name in ("bill", "allocation"):
        form = response.context.get(name)
        if form:
            for field in form:
                value = field.value()
                if hasattr(value, "isoformat"):
                    value = value.isoformat()
                result[field.html_name] = "" if value is None else str(value)
    if response.context.get("review_token"):
        result["review_token"] = response.context["review_token"]
    result.update(changes)
    return result


def allocation_page(client, cycle):
    url = reverse("responsibilities:cycle-shares", args=[cycle.pk])
    details = client.get(url)
    return client.post(url, {"action": "allocate", "baseline": details.context["baseline"]})


def new_bill_page(client, responsibility, **details):
    url = reverse("responsibilities:cycle-stage", args=[responsibility.pk])
    response = client.get(url)
    data = {"baseline": response.context["baseline"], "action": "allocate"}
    data.update({f"bill-{key}": str(value) for key, value in details.items()})
    return client.post(url, data)


def reviewed_save(client, cycle, **changes):
    url = reverse("responsibilities:cycle-shares", args=[cycle.pk])
    page = allocation_page(client, cycle)
    review = client.post(url, payload(page, action="review", **changes))
    assert review.context["step"] == "review", review.context["allocation"].errors
    return client.post(url, payload(review, action="save"))
