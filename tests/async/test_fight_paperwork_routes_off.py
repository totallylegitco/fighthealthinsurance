"""With FIGHT_PAPERWORK_ENABLED off, Fight Paperwork's remaining routes refuse.

The sign-in pages, the REST routes other than the chooser, the appeal PDF
route and the prior auth websocket answer 404 or refuse the connection, and
every chat is a patient chat. FHI's own routes keep answering.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import URLPattern, URLResolver, include, path, reverse
from rest_framework.test import APIClient

from fhi_users import urls as fhi_users_urls
from fhi_users.fight_paperwork import UNAVAILABLE_MESSAGE, gate_patterns
from fhi_users.models import ProfessionalUser
from fighthealthinsurance import rest_urls
from fighthealthinsurance.models import (
    Appeal,
    ChatLeads,
    ChatType,
    InterestedProfessional,
    OngoingChat,
)
from fighthealthinsurance.routing import websocket_urlpatterns
from fighthealthinsurance.websockets import OngoingChatConsumer, resolve_chat_type

User = get_user_model()

PASSWORD = "aLongEnoughPassword-Crumpler-1864"


def _patterns(patterns):
    """Every URLPattern under patterns, following includes."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _patterns(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern


def _assert_refuses(test, pattern) -> None:
    request = RequestFactory().get("/")
    response = pattern.callback(request)
    test.assertEqual(response.status_code, 404, pattern.name)
    test.assertEqual(
        json.loads(response.content), {"error": UNAVAILABLE_MESSAGE}, pattern.name
    )


def _served(request):
    return HttpResponse("served")


@override_settings(FIGHT_PAPERWORK_ENABLED=False)
class GatePatternsTests(TestCase):
    def test_included_patterns_are_gated(self):
        inner = [path("leaf", _served, name="leaf")]
        gated = gate_patterns([path("outer/", include((inner, "app"), namespace="ns"))])
        resolver = gated[0]
        self.assertIsInstance(resolver, URLResolver)
        self.assertEqual((resolver.app_name, resolver.namespace), ("app", "ns"))
        [leaf] = list(_patterns(gated))
        self.assertEqual(leaf.name, "leaf")
        _assert_refuses(self, leaf)

    def test_every_sign_in_route_refuses(self):
        sign_in = list(_patterns(fhi_users_urls.urlpatterns[1:]))
        names = {pattern.name for pattern in sign_in}
        self.assertLessEqual(
            {
                "login",
                "logout",
                "mfa_add_new_trusted_device",
                "verify_email_legacy",
                "mfa_home",
            },
            names,
        )
        for pattern in sign_in:
            _assert_refuses(self, pattern)

    def test_every_fight_paperwork_rest_route_refuses(self):
        chooser_names = {p.name for p in rest_urls.chooser_router.urls}
        fp_names = {p.name for p in rest_urls.router.urls} - chooser_names
        fp_patterns = [
            p for p in _patterns(rest_urls.urlpatterns) if p.name in fp_names
        ]
        self.assertEqual({p.name for p in fp_patterns}, fp_names)
        for pattern in fp_patterns:
            _assert_refuses(self, pattern)


@override_settings(FIGHT_PAPERWORK_ENABLED=False)
class FightPaperworkRoutesOffTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="rebecca_crumpler",
            password=PASSWORD,
            email="rebecca@example.com",
            is_staff=True,
        )
        self.pro_user = User.objects.create_user(
            username="mary_walker", password=PASSWORD, email="mary@example.com"
        )
        self.professional = ProfessionalUser.objects.create(
            user=self.pro_user, active=True, npi_number="1864186418"
        )

    def assert_refused(self, response) -> None:
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": UNAVAILABLE_MESSAGE})

    def test_html_login_is_refused(self) -> None:
        response = self.client.post(
            reverse("login"), {"username": "rebecca_crumpler", "password": PASSWORD}
        )
        self.assert_refused(response)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_and_old_verify_link_are_refused(self) -> None:
        self.assert_refused(self.client.get(reverse("logout")))
        self.assert_refused(
            self.client.get(reverse("verify_email_legacy", args=["MQ", "token"]))
        )

    def test_mfa_pages_are_refused(self) -> None:
        self.client.force_login(self.pro_user)
        self.assert_refused(self.client.get(reverse("mfa_home")))
        self.assert_refused(self.client.get(reverse("mfa_add_new_trusted_device")))

    def test_rest_routes_are_refused_for_a_professional(self) -> None:
        self.client.force_login(self.pro_user)
        for name in (
            "denials-list",
            "chats-list",
            "appeals-list",
            "prior-auth-list",
        ):
            self.assert_refused(self.client.get(reverse(name)))
        self.assert_refused(
            self.client.get(
                reverse("prior-auth-proposals-list", kwargs={"prior_auth_id": "1"})
            )
        )

    def test_chat_lead_signup_is_refused(self) -> None:
        response = self.client.post(
            reverse("chat-leads-list"),
            {
                "name": "Rebecca Lee Crumpler",
                "email": "rebecca@example.com",
                "phone": "555-0100",
                "company": "Crumpler Clinic",
                "consent_to_contact": True,
                "agreed_to_terms": True,
            },
            format="json",
        )
        self.assert_refused(response)
        self.assertFalse(ChatLeads.objects.exists())

    def test_rest_professional_interest_is_refused(self) -> None:
        response = self.client.post(
            reverse("interested-professional-list"),
            {"email": "rebecca@example.com", "name": "Rebecca Lee Crumpler"},
            format="json",
        )
        self.assert_refused(response)
        self.assertFalse(InterestedProfessional.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def _appeal(self) -> Appeal:
        return Appeal.objects.create(
            appeal_text="An appeal.",
            document_enc=SimpleUploadedFile("appeal.pdf", b"PDF bytes"),
        )

    def test_appeal_pdf_is_refused(self) -> None:
        appeal = self._appeal()
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": appeal.uuid})
        )
        self.assert_refused(response)

    def test_appeal_pdf_answers_again_when_on(self) -> None:
        appeal = self._appeal()
        self.client.force_login(self.staff)
        with self.settings(FIGHT_PAPERWORK_ENABLED=True):
            response = self.client.get(
                reverse("appeal_file_view", kwargs={"appeal_uuid": appeal.uuid})
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_chooser_and_ping_still_answer(self) -> None:
        self.assertEqual(self.client.get(reverse("ping")).status_code, 204)
        # An empty vote is a bad request, which shows the route is served.
        response = self.client.post(reverse("chooser-vote"), {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_pro_version_signup_still_creates_a_lead(self) -> None:
        response = Client(enforce_csrf_checks=True).post(
            reverse("pro_version_external_signup"),
            {
                "name": "Rebecca Lee Crumpler",
                "email": "rebecca@clinic.example",
                "job_title_or_provider_type": "Physician",
                "business_name": "Crumpler Clinic",
                "phone_number": "555-0199",
                "most_common_denial": "Prior auth",
                "comments": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            InterestedProfessional.objects.filter(
                email="rebecca@clinic.example"
            ).exists()
        )

    def test_staff_admin_sign_in_still_works(self) -> None:
        client = Client()
        self.assertEqual(client.get("/timbit/admin/login/").status_code, 200)
        response = client.post(
            "/timbit/admin/login/?next=/timbit/admin/",
            {"username": "rebecca_crumpler", "password": PASSWORD},
        )
        self.assertRedirects(response, "/timbit/admin/", fetch_redirect_response=False)
        self.assertEqual(client.get("/timbit/admin/").status_code, 200)


def _websocket(path_: str) -> WebsocketCommunicator:
    return WebsocketCommunicator(URLRouter(websocket_urlpatterns), path_)


@override_settings(FIGHT_PAPERWORK_ENABLED=False)
class FightPaperworkWebsocketsOffTests(TestCase):
    async def test_prior_auth_websocket_is_refused(self) -> None:
        communicator = _websocket("/ws/prior-auth/")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_prior_auth_websocket_connects_when_on(self) -> None:
        with self.settings(FIGHT_PAPERWORK_ENABLED=True):
            communicator = _websocket("/ws/prior-auth/")
            connected, _ = await communicator.connect()
            await communicator.disconnect()
        self.assertTrue(connected)

    async def test_patient_chat_websocket_still_connects(self) -> None:
        communicator = _websocket("/ws/ongoing-chat/")
        connected, _ = await communicator.connect()
        await communicator.disconnect()
        self.assertTrue(connected)


def _get_professional(user):
    return ProfessionalUser.objects.filter(user=user, active=True).first()


@override_settings(FIGHT_PAPERWORK_ENABLED=False)
class FightPaperworkChatsOffTests(TestCase):
    def setUp(self) -> None:
        # The lead row a trial chat's session key matches.
        self.session_key = f"lead-session-{uuid.uuid4().hex}"
        ChatLeads.objects.create(
            name="Rebecca Lee Crumpler",
            email="rebecca@example.com",
            phone="555-0100",
            company="Crumpler Clinic",
            consent_to_contact=True,
            agreed_to_terms=True,
            session_id=self.session_key,
        )
        self.pro_user = User.objects.create_user(
            username="mary_walker", password=PASSWORD, email="mary@example.com"
        )
        self.professional = ProfessionalUser.objects.create(
            user=self.pro_user, active=True, npi_number="1864186418"
        )

    async def _resolve_anonymous(self):
        return await resolve_chat_type(
            user=None,
            is_authenticated=False,
            session_key=self.session_key,
            get_professional_user_fn=_get_professional,
        )

    async def test_lead_holder_gets_a_patient_chat(self) -> None:
        self.assertEqual(await self._resolve_anonymous(), (ChatType.PATIENT, None))

    async def test_lead_holder_gets_a_trial_chat_when_on(self) -> None:
        with self.settings(FIGHT_PAPERWORK_ENABLED=True):
            chat_type, _ = await self._resolve_anonymous()
        self.assertEqual(chat_type, ChatType.TRIAL_PROFESSIONAL)

    async def test_professional_gets_a_patient_chat(self) -> None:
        chat_type, professional_user = await resolve_chat_type(
            user=self.pro_user,
            is_authenticated=True,
            session_key=None,
            get_professional_user_fn=_get_professional,
        )
        self.assertEqual(chat_type, ChatType.PATIENT)
        self.assertIsNone(professional_user)

    async def _stored_trial_chat(self) -> OngoingChat:
        return await OngoingChat.objects.acreate(
            session_key=self.session_key,
            chat_type=ChatType.TRIAL_PROFESSIONAL,
            is_patient=False,
            chat_history=[],
            summary_for_next_call=[],
        )

    async def _stored_professional_chat(self) -> OngoingChat:
        return await OngoingChat.objects.acreate(
            user=self.pro_user,
            professional_user=self.professional,
            chat_type=ChatType.PROFESSIONAL,
            is_patient=False,
            chat_history=[],
            summary_for_next_call=[],
        )

    async def assert_unchanged(self, stored: OngoingChat) -> None:
        fresh = await OngoingChat.objects.aget(id=stored.id)
        self.assertEqual(fresh.chat_type, stored.chat_type)
        self.assertEqual(fresh.is_patient, stored.is_patient)
        self.assertEqual(fresh.user_id, stored.user_id)
        self.assertEqual(fresh.professional_user_id, stored.professional_user_id)

    async def test_reopening_a_trial_chat_starts_a_new_one(self) -> None:
        stored = await self._stored_trial_chat()
        chat = await OngoingChatConsumer()._get_or_create_chat(
            None,
            chat_type=ChatType.PATIENT,
            chat_id=str(stored.id),
            session_key=self.session_key,
            email="rebecca@example.com",
        )
        self.assertNotEqual(chat.id, stored.id)
        self.assertEqual(chat.chat_type, ChatType.PATIENT)
        await self.assert_unchanged(stored)

    async def test_reopening_a_professional_chat_starts_a_new_one(self) -> None:
        stored = await self._stored_professional_chat()
        chat = await OngoingChatConsumer()._get_or_create_chat(
            self.pro_user,
            chat_type=ChatType.PATIENT,
            chat_id=str(stored.id),
            email=self.pro_user.email,
        )
        self.assertNotEqual(chat.id, stored.id)
        self.assertEqual(chat.chat_type, ChatType.PATIENT)
        await self.assert_unchanged(stored)

    async def test_reopening_a_patient_chat_still_works(self) -> None:
        stored = await OngoingChat.objects.acreate(
            session_key=self.session_key,
            chat_type=ChatType.PATIENT,
            is_patient=True,
            chat_history=[],
            summary_for_next_call=[],
        )
        chat = await OngoingChatConsumer()._get_or_create_chat(
            None,
            chat_type=ChatType.PATIENT,
            chat_id=str(stored.id),
            session_key=self.session_key,
            email="rebecca@example.com",
        )
        self.assertEqual(chat.id, stored.id)

    async def test_reopening_a_trial_chat_works_when_on(self) -> None:
        stored = await self._stored_trial_chat()
        with self.settings(FIGHT_PAPERWORK_ENABLED=True):
            chat = await OngoingChatConsumer()._get_or_create_chat(
                None,
                chat_type=ChatType.TRIAL_PROFESSIONAL,
                chat_id=str(stored.id),
                session_key=self.session_key,
            )
        self.assertEqual(chat.id, stored.id)

    async def _chat_frames(self, message: dict) -> list:
        from tests.sync.mock_chat_model import MockChatModel

        mock_model = MockChatModel()
        mock_model.set_persistent_response("A reply.", "Summary.")
        with patch(
            "fighthealthinsurance.ml.ml_router.MLRouter.get_chat_backends"
        ) as backends, patch(
            "fighthealthinsurance.ml.ml_router.MLRouter.get_chat_backends_with_fallback"
        ) as with_fallback, patch(
            "fighthealthinsurance.chat_interface.fire_and_forget_in_new_threadpool",
            new_callable=AsyncMock,
        ):
            backends.return_value = [mock_model]
            with_fallback.return_value = ([mock_model], [])
            communicator = _websocket("/ws/ongoing-chat/")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            frames = []
            try:
                await communicator.send_json_to(message)
                for _ in range(10):
                    frame = await communicator.receive_json_from(timeout=20)
                    frames.append(frame)
                    if "content" in frame or "error" in frame:
                        break
            finally:
                await communicator.disconnect()
        return frames

    async def test_lead_holder_without_email_is_asked_for_one(self) -> None:
        frames = await self._chat_frames(
            {"session_key": self.session_key, "content": "Hello"}
        )
        self.assertEqual(frames, [{"error": "Email is required for patient users."}])
        self.assertFalse(await OngoingChat.objects.aexists())

    async def test_lead_holder_reopening_a_trial_chat_over_the_socket(self) -> None:
        stored = await self._stored_trial_chat()
        frames = await self._chat_frames(
            {
                "chat_id": str(stored.id),
                "session_key": self.session_key,
                "email": "rebecca@example.com",
                "content": "Hello",
            }
        )
        forks = [f for f in frames if f.get("chat_forked")]
        self.assertTrue(forks, frames)
        new_chat = await OngoingChat.objects.aget(id=forks[0]["chat_id"])
        self.assertEqual(new_chat.chat_type, ChatType.PATIENT)
        await self.assert_unchanged(stored)
