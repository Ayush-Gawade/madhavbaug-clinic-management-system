"""Integration tests for the financial module (require PostgreSQL)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models.user import StaffRole

pytestmark = pytest.mark.integration

API = "/api/v1"
PASSWORD = "strong-password-123"


async def _login(client, email: str) -> dict[str, str]:
    response = await client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _register(client, headers: dict[str, str]) -> dict:
    response = await client.post(
        f"{API}/patients",
        headers=headers,
        json={"full_name": "Finance Test Patient"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_treatment(
    client,
    headers: dict[str, str],
    *,
    code: str | None = None,
    price="10000.00",
    royalty="5",
    **overrides,
) -> dict:
    if code is None:
        code = f"PK-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "name": "Panchakarma Full",
        "treatment_code": code,
        "service_category": "Panchakarma",
        "list_price": price,
        "estimated_sessions": 21,
        "royalty_percent": royalty,
        "therapist_cost": "3000",
        "material_cost": "1000",
        "other_direct_cost": "500",
        "overhead_allocation": "500",
        **overrides,
    }
    response = await client.post(f"{API}/treatments", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_owner_creates_and_lists_treatment(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email)
    headers = _headers(tokens)

    treatment = await _create_treatment(client, headers, code="PK-100")
    assert treatment["list_price"] == "10000.00"

    listing = await client.get(f"{API}/treatments", headers=headers)
    assert listing.status_code == 200
    codes = [row["treatment_code"] for row in listing.json()]
    assert "PK-100" in codes

    duplicate = await client.post(
        f"{API}/treatments",
        headers=headers,
        json={
            "name": "Panchakarma Full",
            "treatment_code": "PK-100",
            "list_price": "10000.00",
        },
    )
    assert duplicate.status_code == 409


async def test_estimator_math_and_boundary(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email)
    headers = _headers(tokens)
    treatment = await _create_treatment(client, headers, price="10000.00", royalty="5")

    # 5% royalty on 10,000 -> 500; fixed direct = 3000 + 1000 + 500 = 4500;
    # contribution at 0% discount = 10000 - 500 - 4500 = 5000 -> 50% margin.
    at_zero = await client.post(
        f"{API}/estimator",
        headers=headers,
        json={"treatment_id": treatment["id"], "discount_percent": 0},
    )
    assert at_zero.status_code == 200, at_zero.text
    result = at_zero.json()
    assert Decimal(result["estimated_revenue"]) == Decimal("10000.00")
    assert Decimal(result["royalty"]) == Decimal("500.00")
    assert Decimal(result["contribution"]) == Decimal("5000.00")
    assert not result["violates_boundary"]

    # A 95% discount must breach the boundary.
    extreme = await client.post(
        f"{API}/estimator",
        headers=headers,
        json={"treatment_id": treatment["id"], "discount_percent": 95},
    )
    assert extreme.status_code == 200
    assert extreme.json()["violates_boundary"] is True
    assert extreme.json()["warnings"]


async def test_assign_treatment_payment_and_summary(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    tokens = await _login(client, unique_email)
    headers = _headers(tokens)
    treatment = await _create_treatment(client, headers, code="PK-200")
    patient = await _register(client, headers)

    assigned = await client.post(
        f"{API}/patients/{patient['id']}/treatments",
        headers=headers,
        json={"treatment_id": treatment["id"], "discount_percent": 10},
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["treatment"]["name"] == treatment["name"]

    paid = await client.post(
        f"{API}/patients/{patient['id']}/payments",
        headers=headers,
        json={
            "treatment_id": treatment["id"],
            "amount": "3000",
            "payment_method": "upi",
        },
    )
    assert paid.status_code == 201, paid.text
    assert paid.json()["payment_type"] == "payment"

    summary = await client.get(f"{API}/patients/{patient['id']}/finance", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    # charge = 10000 * (1 - 0.10) = 9000
    assert Decimal(body["total_charges"]) == Decimal("9000.00")
    assert Decimal(body["total_paid"]) == Decimal("3000.00")
    assert Decimal(body["outstanding"]) == Decimal("6000.00")
    assert len(body["lines"]) == 1


async def test_discount_above_default_requires_owner(client, staff_factory, unique_email) -> None:
    doctor_email = f"doctor-{unique_email}"
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    await staff_factory(email=doctor_email, role=StaffRole.DOCTOR)

    owner_headers = _headers(await _login(client, unique_email))
    doctor_headers = _headers(await _login(client, doctor_email))

    treatment = await _create_treatment(client, owner_headers, code="PK-300")
    patient = await _register(client, owner_headers)

    # Default max discount is 50%; a doctor cannot grant 60%.
    denied = await client.post(
        f"{API}/patients/{patient['id']}/treatments",
        headers=doctor_headers,
        json={"treatment_id": treatment["id"], "discount_percent": 60},
    )
    assert denied.status_code == 403

    # The owner can override and it is granted.
    granted = await client.post(
        f"{API}/patients/{patient['id']}/treatments",
        headers=owner_headers,
        json={"treatment_id": treatment["id"], "discount_percent": 60},
    )
    assert granted.status_code == 201


async def test_finance_role_cannot_manage_patients(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.FINANCE)
    tokens = await _login(client, unique_email)

    response = await client.get(f"{API}/patients", headers=_headers(tokens))
    assert response.status_code == 403

    treatments = await client.get(f"{API}/treatments", headers=_headers(tokens))
    assert treatments.status_code == 200


async def _pay(
    client,
    headers: dict[str, str],
    patient_id: str,
    *,
    amount: str,
    payment_type: str = "payment",
    related_payment_id: str | None = None,
):
    payload: dict[str, object] = {"amount": amount, "payment_type": payment_type}
    if related_payment_id is not None:
        payload["related_payment_id"] = related_payment_id
    return await client.post(f"{API}/patients/{patient_id}/payments", headers=headers, json=payload)


async def test_refund_validation(client, staff_factory, unique_email) -> None:
    await staff_factory(email=unique_email, role=StaffRole.OWNER)
    headers = _headers(await _login(client, unique_email))
    patient = await _register(client, headers)
    other = await _register(client, headers)

    payment = await _pay(client, headers, patient["id"], amount="1000")
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["id"]

    # A refund must reference the original payment.
    missing = await _pay(client, headers, patient["id"], amount="100", payment_type="refund")
    assert missing.status_code == 422

    # It must belong to the same patient.
    other_payment = await _pay(client, headers, other["id"], amount="1000")
    assert other_payment.status_code == 201, other_payment.text
    cross_patient = await _pay(
        client,
        headers,
        patient["id"],
        amount="100",
        payment_type="refund",
        related_payment_id=other_payment.json()["id"],
    )
    assert cross_patient.status_code == 409

    # It may not exceed the original amount.
    over = await _pay(
        client,
        headers,
        patient["id"],
        amount="1500",
        payment_type="refund",
        related_payment_id=payment_id,
    )
    assert over.status_code == 409

    # A valid partial refund is accepted and nets against the summary.
    ok = await _pay(
        client,
        headers,
        patient["id"],
        amount="400",
        payment_type="refund",
        related_payment_id=payment_id,
    )
    assert ok.status_code == 201, ok.text

    # A refund cannot reference another refund.
    refund_of_refund = await _pay(
        client,
        headers,
        patient["id"],
        amount="10",
        payment_type="refund",
        related_payment_id=ok.json()["id"],
    )
    assert refund_of_refund.status_code == 409

    # Only refunds may reference an earlier payment.
    stray_reference = await _pay(
        client,
        headers,
        patient["id"],
        amount="10",
        related_payment_id=payment_id,
    )
    assert stray_reference.status_code == 422

    # The remaining refundable balance now caps further refunds: 1000 - 400 = 600.
    remaining_over = await _pay(
        client,
        headers,
        patient["id"],
        amount="700",
        payment_type="refund",
        related_payment_id=payment_id,
    )
    assert remaining_over.status_code == 409
    within = await _pay(
        client,
        headers,
        patient["id"],
        amount="600",
        payment_type="refund",
        related_payment_id=payment_id,
    )
    assert within.status_code == 201, within.text

    summary = await client.get(f"{API}/patients/{patient['id']}/finance", headers=headers)
    assert summary.status_code == 200
    assert Decimal(summary.json()["total_paid"]) == Decimal("0.00")
