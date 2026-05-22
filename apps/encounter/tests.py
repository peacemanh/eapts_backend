from django.test import TestCase
from apps.encounter.models import Encounter
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse

class EncounterModelTest(TestCase):

    def setUp(self):
        self.encounter = Encounter.objects.create()

    def test_encounter_creation(self):
        self.assertIsNotNone(self.encounter.uuid)
        self.assertIsNotNone(self.encounter.date_created)
        self.assertEqual(str(self.encounter), str(self.encounter.uuid))


class EncounterAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('encounter-list')
        # Create an encounter to test
        self.encounter = Encounter.objects.create()

    def test_list_encounters(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_encounter(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('uuid', response.data)
