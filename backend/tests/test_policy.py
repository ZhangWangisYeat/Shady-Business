from app.routing.policy import Candidate, choose_routes, recommended_detour_fraction, shade_weight

FAST=Candidate((1,2),600,480,0)
BALANCED=Candidate((1,3,2),660,210,0)
SHADED=Candidate((1,4,5,2),870,35,0)


def test_cold_route_equals_fastest():
    selected=choose_routes([FAST,BALANCED,SHADED],59)
    assert selected['recommended'] == FAST


def test_hot_weather_increases_shade_priority():
    selected=choose_routes([FAST,BALANCED,SHADED],100.4)
    assert selected['recommended'] == BALANCED
    assert selected['maximum_shade'] == SHADED


def test_unknown_shade_never_claims_better_route():
    candidates=[Candidate((1,2),600,None,600),Candidate((1,3,2),660,None,660)]
    selected=choose_routes(candidates,104)
    assert len(set(s.path for s in selected.values())) == 1


def test_detour_capped():
    selected=choose_routes([FAST,Candidate((1,6,2),1200,0,0)],113)
    assert selected['maximum_shade'] == FAST
    assert selected['recommended'] == FAST


def test_recommended_detour_temperature_bands():
    assert recommended_detour_fraction(76.82) == .15
    assert recommended_detour_fraction(77) == .25
    assert recommended_detour_fraction(85.82) == .25
    assert recommended_detour_fraction(86) == .35


def test_hot_threshold_expands_recommended_route_pool():
    longer_shaded=Candidate((1,7,2),790,0,0)
    assert choose_routes([FAST,longer_shaded],85.82)['recommended'] == FAST
    assert choose_routes([FAST,longer_shaded],86)['recommended'] == longer_shaded


def test_fahrenheit_shade_weight_boundaries():
    assert shade_weight(32) == 0
    assert shade_weight(65) == 0
    assert shade_weight(77.5) == 1
    assert shade_weight(90) == 2
    assert shade_weight(104) == 2
