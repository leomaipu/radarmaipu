from nucleo.geo import haversine_m, point_to_segment_m


def test_haversine_un_grado_de_latitud():
    assert abs(haversine_m(-70.75, -33.5, -70.75, -34.5) - 111_195) < 50


def test_distancia_a_segmento_perpendicular_y_extremo():
    a, b = (-70.76, -33.51), (-70.74, -33.51)
    assert abs(point_to_segment_m(-70.75, -33.509, a, b) - 111.2) < 1
    assert abs(point_to_segment_m(-70.77, -33.51, a, b) - haversine_m(-70.77, -33.51, *a)) < 2
    assert point_to_segment_m(-70.75, -33.51, a, a) < 930
