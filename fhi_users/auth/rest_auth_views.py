from loguru import logger

from rest_framework import status
from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpRequest
import stripe
from django.conf import settings
from django.urls import reverse  # Add this import

from fhi_users.models import UserDomain, ProfessionalUser, ProfessionalDomainRelation
from fhi_users.auth import rest_serializers as serializers
from fhi_users.auth.auth_utils import create_user
from fighthealthinsurance.rest_mixins import CreateMixin, SerializerMixin
from rest_framework.serializers import Serializer


class CreateProfessionalUser(viewsets.ViewSet, CreateMixin):
    """Create a professional user"""

    serializer_class = serializers.ProfessionalSignupSerializer

    def perform_create(
        self, request: HttpRequest, serializer: Serializer
    ) -> Response | serializers.ProfessionalSignupResponseSerializer:
        data: dict[str, str | dict[str, str]] = serializer.validated_data  # type: ignore
        print(data)
        user_signup_info: dict[str, str] = data["user_signup_info"]  # type: ignore
        domain_name: str = user_signup_info["domain_name"]  # type: ignore
        new_domain = data["make_new_domain"]  # type: ignore

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
                # TODO: Get that bag first girl (for now just get users and reconcile post if needed.)
                active=True,
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
            admin=bool(new_domain),
            pending=not new_domain,
        )

        stripe.api_key = settings.STRIPE_API_SECRET_KEY
        # TODO: Reuse product if present
        product = stripe.Product.create(name="Basic Professional Subscription")
        # TODO: Reuse the price if present
        price = stripe.Price.create(
            unit_amount=2500,
            currency="usd",
            recurring={"interval": "month"},
            product=product.id,
        )
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price.id, "quantity": 1}],
            mode="subscription",
            success_url=user_signup_info["continue_url"],
            cancel_url=user_signup_info["continue_url"],
            customer_email=email,
        )
        subscription_id = checkout_session.subscription
        # TODO: Setup webhook to get subscription status and store ID
        return serializers.ProfessionalSignupResponseSerializer(
            {"next_url": checkout_session.url}
        )


class AdminProfessionalUser(viewsets.ViewSet, SerializerMixin):
    """Accept OR reject pending professional user"""

    serializer_class = serializers.AcceptProfessionalUserSerializer

    @action(detail=False, methods=["post"])
    def reject(self, request: HttpRequest) -> Response:
        serializer = self.deserialize(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional_user_id: int = serializer.validated_data["professional_user_id"]
        domain_id: int = serializer.validated_data["domain_id"]
        relation = ProfessionalDomainRelation.objects.get(
            profesional__id=professional_user_id, pending=True, domain__id=domain_id
        )
        relation.pending = False
        # TODO: Add to model
        # relation.rejected = True
        relation.active = False
        relation.save()

    @action(detail=False, methods=["post"])
    def accept(self, request: HttpRequest) -> Response:
        serializer = self.deserialize(data=request.data)
        serializer.is_valid(raise_exception=True)
        professional_user_id: int = serializer.validated_data["professional_user_id"]
        domain_id: int = serializer.validated_data["domain_id"]
        # TODO: Here check and see if the user is an admin user for this domain
        try:
            relation = ProfessionalDomainRelation.objects.get(
                professional_id=professional_user_id, pending=True, domain_id=domain_id
            )
            relation.pending = False
            relation.active = True
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
