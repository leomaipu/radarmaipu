from django.conf import settings


def ajustes_publicos(request):
    return {"RADAR": settings.RADAR}
