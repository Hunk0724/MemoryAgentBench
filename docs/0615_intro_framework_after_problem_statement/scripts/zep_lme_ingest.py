"""Phase 1 of Zep-on-LongMemEval (KU): ingest the OFFICIAL haystack into a
per-question Zep graph, with REAL session timestamps (created_at) so Zep's
temporal KU (valid_at/invalid_at edges) can fire — the faithful, fair setup
(FC used wall-clock; LongMemEval needs the real dates).

Sharding: process questions where idx % NSHARD == SHARD, on the ZEP account given
by env ZEP_API_KEY (the orchestrator assigns one Zep account per shard so the free
plan's per-account quota/throughput is distributed). The SAME idx%N mapping is used
at query time, so each graph is queried on the account that created it.

Chunking: 53% of LongMemEval sessions exceed Zep's ~9998-char graph.add limit, so
each session is split into <=9500-char sub-chunks, ALL carrying that session's date.
Session order == haystack order == timestamp order (haystack is time-sorted).

Usage (one shard):
  ZEP_API_KEY=... python zep_lme_ingest.py --data <json> --nshard N --shard I [--limit M]
"""
import argparse, json, os, re, sys, time
from datetime import datetime, timezone

sys.path.insert(0, __import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from zep_cloud import Zep

GRAPH = lambda cid: f"lme_ku_{cid}"          # per-question graph id
MAXC = 9500                                   # safety margin under Zep's ~9998 limit


def parse_date(s):
    """'2023/04/23 (Sun) 08:57' -> ISO8601 UTC string for graph.add(created_at=)."""
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2}).*?(\d{1,2}):(\d{2})", s or "")
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).isoformat()


def session_text(turns):
    return "\n".join(f"{str(t.get('role','user')).capitalize()}: {t.get('content','')}" for t in turns)


def chunks(text, n=MAXC):
    return [text[i:i + n] for i in range(0, len(text), n)] or [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--qtype", default="knowledge-update")
    ap.add_argument("--nshard", type=int, default=1)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    client = Zep(api_key=os.environ["ZEP_API_KEY"])
    data = json.load(open(args.data))
    items = [d for d in data if d.get("question_type") == args.qtype]
    if args.limit:
        items = items[: args.limit]
    if args.nshard > 1:
        items = [d for i, d in enumerate(items) if i % args.nshard == args.shard]
    print(f"[zep-ingest] {len(items)} '{args.qtype}' (shard {args.shard}/{args.nshard}) "
          f"key=...{os.environ['ZEP_API_KEY'][-6:]}", flush=True)

    t0 = time.time()
    for qi, d in enumerate(items):
        qid = d["question_id"]; cid = qid.replace("-", "_"); g = GRAPH(cid)
        try:
            client.graph.create(graph_id=g)
        except Exception as e:
            if "already exists" not in str(e).lower() and "400" not in str(e):
                print(f"  [{qid}] graph.create err: {repr(e)[:120]}", flush=True)
        n_ep = 0
        ts = time.time()
        for sess, date in zip(d["haystack_sessions"], d.get("haystack_dates", [])):
            iso = parse_date(date)
            for ch in chunks(session_text(sess)):
                if not ch.strip():
                    continue
                for attempt in range(3):
                    try:
                        client.graph.add(graph_id=g, type="text", data=ch,
                                         **({"created_at": iso} if iso else {}))
                        n_ep += 1
                        break
                    except Exception as e:
                        if attempt < 2:
                            time.sleep(5)
                        else:
                            print(f"  [{qid}] graph.add err: {repr(e)[:120]}", flush=True)
        print(f"[zep-ingest] ({qi+1}/{len(items)}) {qid} -> graph {g}: {n_ep} episodes "
              f"({len(d['haystack_sessions'])} sess) {time.time()-ts:.0f}s", flush=True)

    print(f"[zep-ingest] DONE shard {args.shard}/{args.nshard}: {len(items)} graphs "
          f"in {(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
