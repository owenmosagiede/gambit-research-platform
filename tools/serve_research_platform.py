#!/usr/bin/env python3
"""Serve the local UI/API. Run tools/run_research_worker.py separately for execution."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from api.server import make_server

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535')
    root=Path(__file__).resolve().parents[1]
    if root.name!='research_platform':parser.error('Run from research_platform only')
    try:server=make_server(root,port=args.port)
    except OSError:parser.exit(1,'Could not open the local server. Choose another --port if the port is already in use.\n')
    print(f'Research Platform: http://127.0.0.1:{args.port} (web only; separate worker required)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
