#!/usr/bin/env python3
"""One-time live OSM network download. Requires consent to contact Overpass."""
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Download real UCLA pedestrian graph from OpenStreetMap via OSMnx')
    parser.add_argument('--confirm-network',action='store_true',help='I authorize an OSM/Overpass network request')
    parser.add_argument('--radius',type=int,default=1400)
    args=parser.parse_args()
    if not args.confirm_network:
        parser.error('Refusing network request without --confirm-network')
    if not 600 <= args.radius <= 3000:
        parser.error('radius must be 600 to 3000 meters')
    import osmnx as ox
    graph=ox.graph_from_point((34.0689,-118.4452),dist=args.radius,network_type='walk',simplify=True,retain_all=False)
    path=Path(__file__).resolve().parents[1]/'backend/data/ucla_walk.graphml'
    path.parent.mkdir(parents=True,exist_ok=True)
    ox.save_graphml(graph,path)
    print(f'Saved {len(graph.nodes)} nodes and {len(graph.edges)} walk edges: {path}')
    print('Review UCLA campus accessibility, open/closed paths, and graph connectivity before public use.')

if __name__=='__main__': main()
