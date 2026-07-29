from rest_framework import serializers
from .models import ImportLog, ImportUpload


class ImportLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportLog
        fields = [
            'id', 'user', 'publication_year', 'master_source_year', 'mode',
            'status', 'raw_filename', 'validation_report', 'preview_summary',
            'tables_affected', 'faktas_inserted', 'created_at', 'committed_at'
        ]
        read_only_fields = fields


class ImportUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportUpload
        fields = [
            'id', 'user', 'publication_year', 'master_source_year', 'mode',
            'status', 'original_filename', 'validation_report', 'preview_summary',
            'created_at', 'processed_at'
        ]
        read_only_fields = fields
