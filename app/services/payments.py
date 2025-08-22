import stripe
from app.core.settings import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(amount_inr: int, description: str, metadata: dict):
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "inr",
                "product_data": {"name": description},
                "unit_amount": amount_inr * 100,
            },
            "quantity": 1,
        }],
        success_url=f"{settings.BASE_URL}/stripe/success",
        cancel_url=f"{settings.BASE_URL}/stripe/cancel",
        metadata=metadata,
    )
    return session
