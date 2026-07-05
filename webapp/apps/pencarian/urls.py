from django.urls import path

from . import views
from . import api_views

app_name = "pencarian"

urlpatterns = [
    path("", views.cari, name="cari"),
    # API Endpoints (Faceted Search & Time-Series)
    path("api/search/", api_views.FacetedSearchAPIView.as_view(), name="api_search"),
    path("api/timeseries/", api_views.TimeSeriesAPIView.as_view(), name="api_timeseries"),
]
