# GuardEQ

Equilibrium guardrail placement for tool-using LLM agents.

An agent that uses tools reads text from emails, web pages, files and tool outputs, and any of them can
carry a prompt injection. Checking every source with the strongest guardrail is too slow and too
expensive, and a fixed cheaper setup tells an attacker exactly where to go. GuardEQ treats the choice as a
Stackelberg security game: the defender commits to a random mix of guardrails within an average cost
budget, the attacker sees the mix and picks where to strike, and one linear program finds the defender's
best mix.

Term project for ECE-GY 6263 Game Theory (NYU Tandon, Fall 2026), by Rohit Shidid.

## Results (full study, 2,580 logged trials)

Agent, judge and attacker: `gemma4` via Ollama; second model family: `llama3.2`. Report: [`report/report.pdf`](report/report.pdf).

| Question | Answer |
|---|---|
| 1. Lower worst case than simple policies at the same cost? | Yes, at every intermediate budget. At 20% of the judge-everywhere cost: 0.11 vs 0.64 (random) and 0.63 (greedy). |
| 2. Budget to match an LLM judge everywhere? | Exactly only at 100% (the judge had 0/320 successes). Within 0.05 at 60%; safer than classifier-everywhere from 5%. |
| 3. Does an LLM attacker that knows the policy best-respond? | 57% of the time. It attacked tool output (highest damage value) in 98% of 900 runs, a rule of thumb rather than a best response. |
| 4. How sensitive? | Stable to λ and to damage values (policy shift ≤ 0.16). Reusing the gemma4 policy on llama3.2 costs 0.05 in worst case. Planning for the 95% upper bounds, no policy can be certified below 0.16 with 20 trials per cell. |

Realized damage of the equilibrium against the LLM attacker stayed at or below its prediction at every budget
(0.00 / 0.04 / 0.00 at 25 / 50 / 75%). One held-out split attack got past the per-segment LLM judge.

## What is in here

| Path | What it does |
|---|---|
| `guardeq/solver.py` | The linear program, the five baseline policies, and the multiple-LP solver for the general-sum case |
| `guardeq/workspace.py` | Mock workspace and task generator (fake emails, pages, files, tool outputs) |
| `guardeq/attacks.py` | Attack library: direct override, hidden, role-play, split |
| `guardeq/guardrails.py` | The three guardrail levels: none, a small classifier, an LLM judge |
| `guardeq/agent.py` | The target agent's tool loop and the code-checked success conditions |
| `guardeq/attacker.py` | The LLM attacker that is told the policy |
| `guardeq/experiments.py` | The four experiment steps |
| `guardeq/analysis.py`, `report.py`, `demo.py` | Figures, the written report, and the data for the demo page |
| `tests/` | Unit tests, including the worked example from the proposal. They need no model. |
| `data/<profile>/runs.jsonl` | Every trial, with its full transcript |
| `results/<profile>/` | Payoff tables, policies, summaries and figures |
| `docs/index.html` | Static demo that replays saved results |
| `report/` | The report, as Markdown and PDF |
| `presentation/` | Final slides (`GuardEQ_Final_Presentation.pptx`), demo video (`GuardEQ_Demo.mp4`), and the scripts that build them from the results (`node build_deck.js full`, `node record_demo.js`, `python3 build_script.py`) |

## Setup

You need Python 3.10 or newer and [Ollama](https://ollama.com).

```bash
pip install -r requirements.txt
ollama pull gemma4
ollama pull llama3.2
python -m guardeq doctor
```

`doctor` checks the Python packages, that Ollama is reachable, that the models are present, and whether a
Groq key is usable.

## Run it

```bash
python -m unittest discover -s tests          # 25 tests, a second or so, no model needed
python -m guardeq all --profile smoke         # small end-to-end run, about 15 minutes
python -m guardeq all --profile full          # the full study, several hours
```

A run can be stopped at any time. Finished trials are in the log, and the same command picks up where it
left off. Every model call is cached, so repeating a run costs nothing.

| Profile | Attack trials per setting | Normal trials per setting | Attacker runs per policy and budget | Total trials |
|---|---|---|---|---|
| `smoke` | 2 | 2 | 3 | about 230 |
| `reduced` | 15 | 15 | 30 | about 1,740 |
| `full` | 20 | 20 | 50 | about 2,580 |

The `full` profile is the study in the proposal: 1,200 payoff trials and 900 attacker trials, plus 480
trials for the second model family.

Individual steps:

```bash
python -m guardeq payoffs --profile full      # step 1 and 2: measure payoffs, solve
python -m guardeq eval --profile full         # step 3: test against the LLM attacker
python -m guardeq robust --profile full       # step 4: second model family, sensitivity
python -m guardeq analyze --profile full      # rebuild figures from saved results
python -m guardeq report --profile full       # rebuild report/report.md and report.pdf
python -m guardeq demo --profile full         # rebuild docs/data.js for the demo page
python -m guardeq status                      # how many trials each profile has logged
```

## Choosing the LLM judge

The judge guardrail can run locally or on Groq's hosted free tier.

```bash
python -m guardeq all --profile full --judge local    # judge on a local Ollama model (default)
export GROQ_API_KEY=...                                # a key from console.groq.com
python -m guardeq all --profile full --judge groq     # judge on Groq
```

The two are logged separately, so switching back and forth never mixes results. The models can be changed
with environment variables: `GUARDEQ_JUDGE_LOCAL_MODEL` (default `ollama:gemma4`) and
`GUARDEQ_JUDGE_GROQ_MODEL` (default `groq:llama-3.3-70b-versatile`). Only synthetic workspace text is ever
sent to the judge.

## The demo

Open `docs/index.html` in a browser. It reads `docs/data.js` and makes no model calls. To publish it,
enable GitHub Pages for the `docs/` folder of this repository.

## The model in one screen

For entry points `t`, guardrail levels `l` and attack types `a`:

```
minimize    z + lambda * sum_t f_t sum_l c[t,l] r[t,l]
subject to  z >= V_t * sum_l c[t,l] p[t,l,a]        for every t, a
            sum_l c[t,l] = 1                        for every t
            sum_t f_t sum_l c[t,l] k_l <= B,        c >= 0
```

`p` is the measured chance an attack succeeds, `r` the measured chance a normal task is wrongly blocked,
`k` the measured delay of one check, `V` the damage value of an entry point, `f` its traffic weight, and
`B` the average cost budget per task. `c` is the defender's mix and `z` the worst-case damage.

Worked example: two entry points of equal value, one attack type, a judge that stops 80% of attacks, and
budget for one judge per task. Any fixed placement has a worst case of 1.0. Mixing half and half brings it
to 0.6 at the same cost. `tests/test_solver.py` checks this.

## Safety

Everything runs against a synthetic workspace. There are no real accounts, credentials or data, the
attacker addresses use the reserved `.test` domain, and the "tools" the agent calls do nothing.

## License

MIT
