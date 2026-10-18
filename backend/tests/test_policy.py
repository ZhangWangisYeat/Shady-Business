from app.routing.policy import Candidate, choose_routes, recommended_detour_fraction

FAST=Candidate((1,2),600,480,0)
BALANCED=Candidate((1,3,2),660,210,0)
SHADED=Candidate((1,4,5,2),870,35,0)


def test_cold_route_equals_fastest():
    selected=choose_routes([FAST,BALANCED,SHADED],15)
    assert selected['recommended'] == FAST


def test_hot_weather_increases_shade_priority():
    selected=choose_routes([FAST,BALANCED,SHADED],38)
    assert selected['recommended'] == BALANCED
    assert selected['maximum_shade'] == SHADED


def test_unknown_shade_never_claims_better_route():
    candidates=[Candidate((1,2),600,None,600),Candidate((1,3,2),660,None,660)]
    selected=choose_routes(candidates,40)
    assert len(set(s.path for s in selected.values())) == 1


def test_detour_capped():
    selected=choose_routes([FAST,Candidate((1,6,2),1200,0,0)],45)
    assert selected['maximum_shade'] == FAST
    assert selected['recommended'] == FAST


def test_recommended_detour_temperature_bands():
    assert recommended_detour_fraction(24.9) == .15
    assert recommended_detour_fraction(25) == .25
    assert recommended_detour_fraction(29.9) == .25
    assert recommended_detour_fraction(30) == .35


def test_hot_threshold_expands_recommended_route_pool():
    longer_shaded=Candidate((1,7,2),790,0,0)
    assert choose_routes([FAST,longer_shaded],29.9)['recommended'] == FAST
    assert choose_routes([FAST,longer_shaded],30)['recommended'] == longer_shaded
