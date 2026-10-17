import networkx as nx
from app.routing.graph import candidate_paths,coords_for_edge,snap_node


def test_connected_fixture_paths_no_network():
    g=nx.MultiDiGraph()
    g.add_node('a',x=-118.443,y=34.071)
    g.add_node('b',x=-118.442,y=34.071)
    g.add_node('c',x=-118.442,y=34.070)
    g.add_edge('a','b',length=90.)
    g.add_edge('b','c',length=100.)
    g.add_edge('a','c',length=300.)
    assert candidate_paths(g,'a','c',limit=2)==[['a','b','c'],['a','c']]
    assert coords_for_edge(g,'a','b')[0]==(-118.443,34.071)
    assert snap_node(g,(-118.443,34.071))=='a'
