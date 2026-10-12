from django.urls import path, re_path
from . import views
urlpatterns = [path('', views.about), path('about/', views.about), path('healthz', views.health),
    path('login/', views.sign_in), path('logout/', views.sign_out),
    path('public/<str:name>', views.public_asset), path('api/<path:endpoint>', views.api),
    re_path(r'^.*$', views.private_asset)]
