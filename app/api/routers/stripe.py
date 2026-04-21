"""
Stripe webhook handler.

Tier changes are driven entirely by Stripe events — the users table is always
the source of truth for the current tier.

Register POST /webhooks/stripe in the Stripe dashboard with these events:
  - customer.subscription.created
  - customer.subscription.updated
  - customer.subscription.deleted
  - invoice.payment_failed
  - invoice.payment_succeeded
"""

from __future__ import annotations

import logging
import os

import stripe
from fastapi import APIRouter, HTTPException, Request

from api.tiers import STRIPE_PRICE_TO_TIER
from db.schema import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stripe"])


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _update_user_tier(stripe_customer_id: str, tier: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET tier = %s, subscription_status = %s, updated_at = NOW()
            WHERE stripe_customer_id = %s
            """,
            (tier, status, stripe_customer_id),
        )


def _update_subscription_status(stripe_customer_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET subscription_status = %s, updated_at = NOW() WHERE stripe_customer_id = %s",
            (status, stripe_customer_id),
        )


def _resolve_tier_from_subscription(subscription: dict) -> str | None:
    """Extract the first price ID from a subscription and map it to a tier."""
    items = subscription.get("items", {}).get("data", [])
    for item in items:
        price_id = item.get("price", {}).get("id")
        if price_id and price_id in STRIPE_PRICE_TO_TIER:
            return STRIPE_PRICE_TO_TIER[price_id]
    return None


def _resolve_tier_from_invoice(invoice: dict) -> str | None:
    """Extract price ID from an invoice's line items and map to a tier."""
    lines = invoice.get("lines", {}).get("data", [])
    for line in lines:
        price_id = (line.get("price") or {}).get("id")
        if price_id and price_id in STRIPE_PRICE_TO_TIER:
            return STRIPE_PRICE_TO_TIER[price_id]
    return None


# ─── Webhook endpoint ─────────────────────────────────────────────────────────

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not webhook_secret:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not configured")

    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        logger.exception("Failed to construct Stripe event")
        raise HTTPException(status_code=400, detail=str(exc))

    event_type = event["type"]
    logger.info("Stripe webhook: %s", event_type)

    try:
        match event_type:
            case "customer.subscription.created" | "customer.subscription.updated":
                subscription = event["data"]["object"]
                customer_id = subscription["customer"]
                tier = _resolve_tier_from_subscription(subscription)
                status = subscription.get("status", "active")
                if tier:
                    _update_user_tier(customer_id, tier, status)
                    logger.info("Updated user tier to %s (customer=%s)", tier, customer_id)
                else:
                    logger.warning("Unknown price in subscription for customer %s", customer_id)

            case "customer.subscription.deleted":
                subscription = event["data"]["object"]
                customer_id = subscription["customer"]
                _update_user_tier(customer_id, "free", "cancelled")
                logger.info("Subscription cancelled — reverted to free (customer=%s)", customer_id)

            case "invoice.payment_failed":
                invoice = event["data"]["object"]
                customer_id = invoice["customer"]
                _update_subscription_status(customer_id, "past_due")
                logger.info("Payment failed — marked past_due (customer=%s)", customer_id)

            case "invoice.payment_succeeded":
                invoice = event["data"]["object"]
                customer_id = invoice["customer"]
                tier = _resolve_tier_from_invoice(invoice)
                if tier:
                    _update_user_tier(customer_id, tier, "active")
                    logger.info("Payment succeeded — restored tier %s (customer=%s)", tier, customer_id)
                else:
                    _update_subscription_status(customer_id, "active")

            case _:
                logger.debug("Unhandled Stripe event: %s", event_type)

    except Exception:
        logger.exception("Error processing Stripe event %s", event_type)
        raise HTTPException(status_code=500, detail="Error processing webhook")

    return {"received": True}
