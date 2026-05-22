from django.test import TestCase
from apps.data_element.models import DataElement
from .models import AggregateRecord

class AggregateRecordTestCase(TestCase):
    def setUp(self):
        self.form = DataElement.objects.create(name='MPT Form', label='MPT Form', class_id_id=1, datatype_id_id=1)
        self.question = DataElement.objects.create(name='Number of Clients', label='Number of Clients', class_id_id=1, datatype_id_id=2)

    def test_create_record(self):
        record = AggregateRecord.objects.create(
            data_element=self.question,
            form=self.form,
            value_numeric=10
        )
        self.assertEqual(record.value_numeric, 10)

    def test_bulk_insert(self):
        from .serializers import AggregateRecordSerializer
        data = [
            {"form": self.form.id, "data_element": self.question.id, "value": "15"},
            {"form": self.form.id, "data_element": self.question.id, "value": "20"}
        ]
        serializer = AggregateRecordSerializer(data=data, many=True, context={'request': None})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        self.assertEqual(AggregateRecord.objects.count(), 2)
