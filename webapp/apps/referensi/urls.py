from django.urls import path
from . import views

app_name = 'referensi'

urlpatterns = [
    path('cleaning/', views.DataCleaningDashboardView.as_view(), name='cleaning_dashboard'),
    path('cleaning/preview/', views.EntityPreviewAPIView.as_view(), name='preview_entity'),
    path('cleaning/merge/', views.MergeEntitiesView.as_view(), name='merge_entities'),
    path('cleaning/history/', views.MergeHistoryAPIView.as_view(), name='merge_history'),
    path('cleaning/undo/', views.UndoMergeAPIView.as_view(), name='undo_merge'),
    path('cleaning/autoclean/', views.AutoCleanBracketsAPIView.as_view(), name='auto_clean'),
    path('cleaning/suggestions/', views.SmartSuggestionAPIView.as_view(), name='smart_suggestions'),
]
