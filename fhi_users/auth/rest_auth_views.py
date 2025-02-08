from loguru import logger
from typing import Optional

from rest_framework import status
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import permissions


from django.http import HttpRequest
from django.conf import settings
from django.urls import reverse
from django.contrib.auth import get_user_model

import stripe

from fhi_users.models import UserDomain, ProfessionalUser, ProfessionalDomainRelation
from fhi_users.auth import rest_serializers as serializers
from fhi_users.auth.auth_utils import create_user
from fighthealthinsurance.rest_mixins import CreateMixin, SerializerMixin
from rest_framework.serializers import Serializer
from fighthealthinsurance import stripe_utils

User = get_user_model()


class CreateProfessionalUser(viewsets.ViewSet, CreateMixin):
    """Create a professional user"""

    serializer_class = serializers.ProfessionalSignupSerializer

    def perform_create(
        self, request: HttpRequest, serializer: Serializer
    ) -> Response | serializers.ProfessionalSignupResponseSerializer:
        data: dict[str, str | dict[str, str]] = serializer.validated_data  # type: ignore
        user_signup_info: dict[str, str] = data["user_signup_info"]  # type: ignore
        domain_name: str = user_signup_info["domain_name"]  # type: ignore
        new_domain: bool = bool(data["make_new_domain"])  # type: ignore

        if not new_domain:
            try:
                UserDomain.objects.filter(name=domain_name).get()
            except UserDomain.DoesNotExist:
                return Response(
                    {"error": "Domain does not exist"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            if UserDomain.objects.filter(name=domain_name).count() != 0:
                return Response(
                    {"error": "Domain already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if "user_domain" not in data:
                return Response(
                    {
                        "error": "Need domain info when making a new domain or solo provider"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user_domain_info: dict[str, str] = data["user_domain"]  # type: ignore
            if domain_name != user_domain_info["name"]:
                return Response(
                    {"error": "Domain name and user domain name must match"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            UserDomain.objects.create(
                active=False,
                **user_domain_info,
            )

        user_domain: UserDomain = UserDomain.objects.get(name=domain_name)
        raw_username: str = user_signup_info["username"]  # type: ignore
        email: str = user_signup_info["email"]  # type: ignore
        password: str = user_signup_info["password"]  # type: ignore
        first_name: str = user_signup_info["first_name"]  # type: ignore
        last_name: str = user_signup_info["last_name"]  # type: ignore
        user = create_user(
            raw_username=raw_username,
            domain_name=domain_name,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        professional_user = ProfessionalUser.objects.create(
            user=user,
            active=False,
        )
        ProfessionalDomainRelation.objects.create(
            professional=professional_user,
            domain=user_domain,
            active=False,
            admin=new_domain,
            pending=True,
        )

        stripe.api_key = settings.STRIPE_API_SECRET_KEY
        # Check if the product already exists
        products = stripe.Product.list(limit=100)
        product = next(
            (p for p in products.data if p.name == "Basic Professional Subscription"),
            None,
        )

        if product is None:
            product = stripe.Product.create(name="Basic Professional Subscription")

        # Check if the price already exists for the product
        prices = stripe.Price.list(product=product["id"], limit=100)
        product_price = next(
            (
                p
                for p in prices.data
                if p.unit_amount == 2500
                and p.currency == "usd"
                and p.id == product["id"]
            ),
            None,
        )

        if product_price is None:
            product_price = stripe.Price.create(
                unit_amount=2500, currency="usd", product=product["id"]
            )
        items = [
            {
                "price": product_price["id"],
                "quantity": 1,
            }
        ]

        product_id, price_id = stripe_utils.get_or_create_price(
            "Basic Professional Subscription", 2500, recurring=True
        )

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=user_signup_info["continue_url"],
            cancel_url=user_signup_info["continue_url"],
            customer_email=email,
            metadata={
                "payment_type": "professional_domain_subscription",
                "professional_id": str(professional_user.id),
                "domain_id": str(user_domain.id),
            },
        )
        subscription_id = checkout_session.subscription
        return serializers.ProfessionalSignupResponseSerializer(
            {"next_url": checkout_session.url}
        )


class AdminProfessionalUser(viewsets.ViewSet, SerializerMixin):
    """Accept OR reject pending professional user"""

    serializer_class = serializers.AcceptProfessionalUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["post"])
    def reject(self, request) -> Response:
        serializer = self.deserialize(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional_user_id: int = serializer.validated_data["professional_user_id"]
        domain_id: int = serializer.validated_data["domain_id"]
        # TODO: Check auth here
        relation = ProfessionalDomainRelation.objects.get(
            professional_id=professional_user_id, pending=True, domain_id=domain_id
        )
        relation.pending = False
        # TODO: Add to model
        relation.rejected = True
        relation.active = False
        relation.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def accept(self, request) -> Response:
        serializer = self.deserialize(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional_user_id: int = serializer.validated_data["professional_user_id"]
        domain_id: int = serializer.validated_data["domain_id"]
        # TODO: Here check and see if the user is an admin user for this domain
        try:
            current_user: User = request.user  # type: ignore
            current_user_admin_in_domain = (
                ProfessionalDomainRelation.objects.filter(
                    professional__user=current_user,
                    domain_id=domain_id,
                    admin=True,
                    pending=False,
                    active=True,
                ).count()
                > 0
            )
            if not current_user_admin_in_domain:
                # Credentials are valid but does not have permissions
                return Response(status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            # Unexecpted generic error, fail closed
            logger.opt(exception=e).error("Error in accepting professional user")
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        try:
            relation = ProfessionalDomainRelation.objects.get(
                professional_id=professional_user_id, pending=True, domain_id=domain_id
            )
            professional_user = ProfessionalUser.objects.get(id=professional_user_id)
            professional_user.active = True
            professional_user.save()
            relation.pending = False
            relation.save()

            stripe.api_key = settings.STRIPE_API_SECRET_KEY
            if relation.domain.stripe_subscription_id:
                subscription = stripe.Subscription.retrieve(
                    relation.domain.stripe_subscription_id
                )
                stripe.Subscription.modify(
                    subscription.id,
                    items=[
                        {
                            "id": subscription["items"]["data"][0].id,
                            "quantity": subscription["items"]["data"][0].quantity + 1,
                        }
                    ],
                )
            else:
                logger.debug("Skipping no subscription present.")

            return Response({"status": "accepted"}, status=status.HTTP_200_OK)
        except ProfessionalDomainRelation.DoesNotExist:
            return Response(
                {"error": "Relation not found or already accepted"},
                status=status.HTTP_404_NOT_FOUND,
            )
