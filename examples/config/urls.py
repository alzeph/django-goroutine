from django.urls import include, path

urlpatterns = [
    path("", include("playground.urls")),
]
