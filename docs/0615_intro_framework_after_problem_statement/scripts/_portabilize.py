"""One-off: replace hardcoded /home/yhchiang/... paths in the recent run/analysis
scripts with portable env-vars-with-defaults so the repo runs on any machine
(Linux/Mac/Windows-GitBash) without editing. Idempotent.

.sh  : inject REPO_ROOT / CONDA_SH / LME_DATA(_DIR) header after `set -u`; route
       conda + repo + LME data + judge paths through them.
.py  : ROOT / sys.path.insert -> $REPO_ROOT or Path(__file__).parents[3].
"""
import os, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
SH_HEADER = (
    'REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." && pwd)}"\n'
    'CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"\n'
    'LME_DATA_DIR="${LME_DATA_DIR:-$REPO_ROOT/data/longmemeval}"\n'
    'export LME_DATA="${LME_DATA:-$LME_DATA_DIR/longmemeval_s_cleaned.json}"\n'
)
PY_ROOT = ('__import__("os").environ.get("REPO_ROOT") or str(__import__("pathlib").Path(__file__).resolve().parents[3])')

def do_sh(p):
    s = open(p).read()
    if "REPO_ROOT:-" not in s:  # inject header once, after `set -u` (else after shebang)
        if re.search(r'^set -u\b', s, re.M):
            s = re.sub(r'(^set -u\b.*\n)', r'\1' + SH_HEADER, s, count=1, flags=re.M)
        else:
            s = re.sub(r'(\A#![^\n]*\n)', r'\1' + SH_HEADER, s, count=1)
    # python-heredoc data references (single-quoted full path) -> os.environ
    s = s.replace("'/home/yhchiang/LongMemEval/data/longmemeval_s_cleaned.json'", "os.environ['LME_DATA']")
    # conda source line
    s = re.sub(r'source\s+\S*miniconda3/etc/profile\.d/conda\.sh', 'source "$CONDA_SH"', s)
    # judge (external repo) -> in-repo alternative
    s = s.replace("/home/yhchiang/origin_longmemeval/LongMemEval/src/evaluation/evaluate_qa.py",
                  "$REPO_ROOT/llm_based_eval/longmem_qa_evaluate.py")
    # remaining shell paths
    s = s.replace("/home/yhchiang/LongMemEval/data", "$LME_DATA_DIR")
    s = s.replace("/home/yhchiang/MemoryAgentBench", "$REPO_ROOT")
    open(p, "w").write(s)

def do_py(p):
    s = open(p).read()
    s = re.sub(r'(ROOT\s*=\s*)"(/home/yhchiang/MemoryAgentBench)"', r'\1' + PY_ROOT, s)
    s = re.sub(r'sys\.path\.insert\(0,\s*"(/home/yhchiang/MemoryAgentBench)"\)',
               'sys.path.insert(0, ' + PY_ROOT + ')', s)
    s = s.replace('"/home/yhchiang/LongMemEval/data', 'os.environ.get("LME_DATA_DIR", os.path.join('
                  + PY_ROOT + ', "data/longmemeval")) + "')  # rare; most .py take --data
    open(p, "w").write(s)

ch = 0
for p in sorted(glob.glob(f"{HERE}/*.sh")):
    before = open(p).read(); do_sh(p)
    if open(p).read() != before: ch += 1; print("  sh ", os.path.basename(p))
for p in sorted(glob.glob(f"{HERE}/*.py")):
    if os.path.basename(p) == "_portabilize.py": continue
    before = open(p).read(); do_py(p)
    if open(p).read() != before: ch += 1; print("  py ", os.path.basename(p))
print(f"portabilized {ch} files")
