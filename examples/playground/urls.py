from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("parallel/", views.parallel_view, name="parallel"),
    path("cpu-map/", views.cpu_map_view, name="cpu-map"),
    path("timeout/", views.timeout_view, name="timeout"),
    path("errors/", views.errors_view, name="errors"),
    path("backpressure/", views.backpressure_view, name="backpressure"),
]
