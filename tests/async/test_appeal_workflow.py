import pytest
import uuid as uuid_lib
from django.test import TestCase, AsyncClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from fighthealthinsurance.models import Appeal, ProfessionalUser, Denial
from asgiref.sync import sync_to_async

@pytest.mark.django_db
class TestAppealWorkflow(TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up class-level test data"""
        super().setUpClass()
        cls.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.professional_user = ProfessionalUser.objects.create(
            user=cls.user,
            active=True
        )

    async def setUp(self):
        """Set up test data"""
        self.client = AsyncClient()
        
        create_denial = sync_to_async(Denial.objects.create)
        self.test_denial = await create_denial(
            denial_type='medical_necessity',
            insurance_company='Test Insurance',
            hashed_email='test@example.com'
        )
        
        create_appeal = sync_to_async(Appeal.objects.create)
        self.test_appeal = await create_appeal(
            uuid=str(uuid_lib.uuid4()),
            appeal_text="Test appeal",
            hashed_email='test@example.com',
            creating_professional=self.professional_user,
            denial=self.test_denial
        )

    async def test_async_home_view(self):
        """Test the async home view"""
        url = reverse('root')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    async def test_async_api_endpoint(self):
        """Test async API endpoint"""
        url = reverse('process')
        data = {
            'email': 'test@example.com',
            'message': 'test',
            'denial_type': 'medical_necessity',
            'insurance_company': 'Test Insurance'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)

    @classmethod
    async def asyncTearDown(cls):
        """Clean up after all tests"""
        delete_denials = sync_to_async(Denial.objects.all().delete)
        delete_appeals = sync_to_async(Appeal.objects.all().delete)
        await delete_denials()
        await delete_appeals()

    @classmethod
    def tearDownClass(cls):
        """Clean up after class"""
        super().tearDownClass()