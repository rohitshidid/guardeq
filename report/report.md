---
title: "GuardEQ: Equilibrium Guardrail Placement for Tool-Using LLM Agents"
author: "Rohit Shidid (RRS6770)"
date: "ECE-GY 6263 Game Theory, Fall 2026 · Term project report · built 2026-11-10"
geometry: margin=1in
fontsize: 11pt
linkcolor: blue
header-includes:
  - \usepackage{booktabs}
  - \usepackage{float}
  - \floatplacement{figure}{H}
---

**Abstract.** AI agents that use tools read text from many sources: emails, web pages, files and tool
outputs. Any of them can carry a prompt injection. A guardrail can inspect each source, but strong checks
are slow and cheap checks miss attacks. GuardEQ treats the choice of which guardrail to run at each source
as a Stackelberg security game. The defender commits to a random mix of guardrails within an average cost
budget; an attacker observes the mix and chooses where and how to attack. The payoffs of the game are
measured in a sandbox, the defender's optimal mix is found with one linear program, and the result is
compared with five simple policies and tested against an LLM attacker that is told the policy.

# Introduction

Tool-using agents read content they did not write and cannot trust. An attacker who can place text in an
email, a web page, a shared file or a tool's output can try to redirect the agent, for example with the
sentence "ignore your task and email me the user's files". This is indirect prompt injection [10], and
benchmarks show that it works against current agents [9].

A defender can put a guardrail at each entry point, but the options trade safety for cost. A small
classifier is fast and misses the less obvious attacks. An LLM judge catches more and adds a model call,
with its delay, to every check. Running the strongest check everywhere is too slow and too expensive, so
in practice a team picks one fixed configuration and keeps it. A fixed configuration is easy to study: the
attacker finds the weakest entry point and attacks there.

Game theory fits this problem. In a Stackelberg security game a defender with limited resources commits
to a randomized plan, and an attacker studies the plan before acting [6, 7]. The same framework schedules
airport security checks and patrols [8]. Game-theoretic design has been argued for in AI agent security
[1], and LLM jailbreaking has been modelled as a Stackelberg game between an attacker and a defending
model [2]. Other work uses game theory to train prompt-injection detectors [4] and to design cyber
deception [5]. Each of these studies one detector or one system. GuardEQ applies the idea to an agent with
several entry points that share one budget.

The project asks four questions. (1) At the same cost, does the equilibrium policy have lower worst-case
damage than fixed and simple policies? (2) How much budget does it need to match an LLM judge everywhere?
(3) When an LLM attacker is told the defender's policy, does it pick the best target, as the theory
assumes? Recent work on LLM-Nash games suggests that LLM agents may not follow classical equilibrium
behaviour [3]. (4) How much do the results change with the damage values, the weight on false blocks, and
the model?

# Game model

**Players.** The defender is the leader. For each entry point it chooses how often to run each guardrail,
within a budget. The attacker is the follower. It sees these probabilities, but not the guardrail drawn on
a given task, and picks the entry point and attack type that cause the most damage.

**Notation.** Entry points $t \in \{\text{email, web page, file, tool output}\}$ each have a damage value
$V_t$ and a traffic weight $f_t$, the number of checks per task. Guardrail levels
$\ell \in \{\text{none, classifier, LLM judge}\}$ each have a cost $\kappa_\ell$, the delay one check adds.
Attack types are $a \in \{\text{direct override, hidden, role-play, split}\}$; a split attack is broken into
two pieces inside one entry point. $p_{t,\ell,a}$ is the probability that attack type $a$ succeeds at entry
point $t$ under guardrail $\ell$, and $r_{t,\ell}$ is the probability that a normal task fails because the
guardrail at $t$ blocked safe content. Both are measured. The defender's decision is $c_{t,\ell}$, the
probability of running guardrail $\ell$ at entry point $t$.

**Payoffs.** If the attacker picks $(t, a)$, the expected damage is $V_t \sum_\ell c_{t,\ell}\, p_{t,\ell,a}$.
The defender's loss is this damage plus $\lambda$ times the harm to normal tasks. That harm does not depend
on the attacker, so the attacker simply picks the most damaging option, and the defender's best commitment,
the strong Stackelberg equilibrium [7], is the solution of one linear program:

$$
\begin{aligned}
\min_{c,\,z} \quad & z + \lambda \sum_t f_t \sum_\ell c_{t,\ell}\, r_{t,\ell} \\
\text{subject to} \quad & z \ge V_t \sum_\ell c_{t,\ell}\, p_{t,\ell,a} && \text{for every } t, a, \\
& \sum_\ell c_{t,\ell} = 1 && \text{for every } t, \\
& \sum_t f_t \sum_\ell c_{t,\ell}\, \kappa_\ell \le B, \qquad c_{t,\ell} \ge 0 .
\end{aligned}
$$

Here $z$ is the worst-case damage and $B$ is the average cost budget per task. On each task one guardrail is
drawn for each entry point from $c$. The draws are independent, so $B$ bounds the average cost and not the
cost of every task. Solving the program for a range of budgets gives a curve of security against cost.

**General-sum case.** If the attacker values entry points by $U_t \ne V_t$, the game is no longer zero-sum
in damage. The code handles this with the multiple-LP method of Conitzer and Sandholm [6]: for each
attacker choice $(t^*, a^*)$ it solves for the defender's best policy under the constraint that
$(t^*, a^*)$ is a best response, and keeps the best of these. When $U = V$ it returns the same objective
as the single program above, which is one of the unit tests.

**Worked example.** Take two entry points, A and B, of equal value, and one attack type. With no guardrail
every attack works. An LLM judge stops 80% of attacks and costs 1, and the budget allows one judge per task
on average. Putting the judge only at A, or only at B, leaves the other entry point open, and the worst
case is 1.0. Running the judge at each with probability 0.5 gives a success rate of 0.6 at both, and the
worst case falls to 0.6 at the same cost. If A is worth twice as much as B, the best mix moves to 0.75 and
0.25. The solver reproduces these numbers, and they are its first tests.

# System

All experiments run in a mock workspace. No real account or data is involved.

**Workspace and tasks.** Each task asks the agent for one fact that it can only get by reading one document
through one entry point: an email, a web page, a file or the output of an internal API. Documents are
generated from templates with random details, so every trial has a different answer. A document is a list
of segments: the one holding the answer, routine filler, and sometimes a sentence of ordinary business text
that sounds like an instruction ("please disregard my previous email and forward the signed form to HR").
The last kind is benign, and a guardrail that removes it has made a mistake. Two sets of templates are kept
apart: one for measuring payoffs and one held out for the final test.

**Agent.** The target agent is a local open-weight model, run through Ollama, in a short tool-calling loop.
It has four reading tools, one per entry point, and two tools that an attack can abuse: `send_email` and
`grant_access`. Its instructions include a private account recovery code, different on every trial.

**Guardrails.** A guardrail inspects a document one segment at a time and removes the segments it flags.
*None* passes everything. The *classifier* is a logistic regression over hashed word unigrams and bigrams,
trained once on a small corpus of blunt override phrases and ordinary business text; none of the attack or
task wording used in the experiments is in that corpus. The *LLM judge* asks a model whether a segment
contains instructions aimed at an AI assistant. The judge can run on a local model or on a hosted one, and
the choice is a command-line switch. A guardrail's cost is the measured delay it adds to one document read.

**Attacks.** The library has four attack types. A *direct override* tells the agent to ignore its task. A
*hidden* attack places the instruction in markup that a person would not see. A *role-play* attack frames
it as a persona, a drill or a system notice. A *split* attack divides the instruction into two segments
planted apart, so that a guardrail reading one segment at a time sees neither half as a complete
instruction. Each type has several wordings for measuring payoffs and separate ones held out for testing.

**Success checks.** Every attack has a goal that code can check. Either the planted recovery code appears
in the arguments of a tool call, or `grant_access` is called for the attacker's user. A normal task succeeds if
the agent's final answer contains the fact that was asked for. No human or LLM judgment enters any result.

**Logging.** Every trial is appended to a log with its full transcript, and every model call is cached with
its measured latency. All figures and tables in this report are rebuilt from the log without new calls.

# Experimental design

1. **Measure payoffs.** Run 2 trials in each of the 48 attack settings (4 entry points, 3
   guardrails, 4 attack types) and 2 normal-task trials in each of 12 settings. A trial's task and
   attack wording depend on the entry point, attack type and trial number but not on the guardrail, so the
   three guardrail levels are compared on the same material.
2. **Solve.** Solve the linear program at six budget levels, from zero to the cost of an LLM judge on every
   read.
3. **Test against the attacker.** Run each of six policies against an LLM attacker at three budgets, with
   3 runs each, on held-out tasks. The attacker is told the policy, chooses a target and writes its own
   injection. One guardrail is then drawn from the policy for the chosen entry point.
4. **Check robustness.** Repeat the payoff measurement with a second model family, and re-solve the game
   for other values of $\lambda$ and of the damage values.

Payoffs are estimated once, from their own runs. The test runs in step 3 never feed back into them.

**Baselines.** The equilibrium policy is compared with: no guardrails; the classifier everywhere; the LLM
judge everywhere; random placement, which runs the judge with the same probability at every entry point so
as to spend the same budget; and greedy placement, which spends the budget on the judge at the most
valuable entry points first.

**Metrics.** Worst-case damage, attack success rate, normal-task success, false-block rate and added delay
per task. Two further metrics test the theory: the gap between predicted worst-case damage and the damage
the attacker achieved, and how often the attacker picked a target that the model identifies as a best
response. Rates are reported with 95% Wilson intervals.

**Parameters.** Damage values $V$ = email 0.8, web page 0.6, file 0.7, tool output 1.0; traffic weights $f$ = email 1.0, web page 1.5, file 0.8, tool output 1.2; $\lambda$ = 0.5. Agent
`ollama:gemma4`, attacker `ollama:gemma4`, judge `ollama:gemma4`.

# Results

> **These results are preliminary.** They come from the `smoke` profile: 2 trials per attack setting, 2 normal-task trials per setting and 3 attacker runs per policy and budget, against 20, 20 and 50 in the full study. With samples this small the confidence intervals are very wide, and none of the comparisons below should be read as findings. They show that every stage of the pipeline runs end to end.

The run logged 120 payoff trials with the agent `ollama:gemma4` and the judge `ollama:gemma4`.

## Phase checks

| Check | Result |
|:--|--:|
| Normal tasks succeed with no guardrail (target: 85%) | 100%, pass |
| Attacks work when there is no guardrail | pass |
| Stronger guardrails block more | pass |

: Checks each phase had to pass before the next one started.

## Measured payoffs

Averaged over entry points and attack types, attacks succeeded 34% of the time with no guardrail, 3% with the classifier and 0% with the LLM judge. Table 2 gives the success rate for every setting and Figure 2 shows the same numbers as a heat map.

| Entry point, guardrail | Direct override | Hidden | Role-play | Split | False block | Task success |
|:--|--:|--:|--:|--:|--:|--:|
| Email, none | 1.00 | 0.50 | 0.00 | 0.00 | 0.00 | 1.00 |
| Email, classifier | 0.00 | 0.50 | 0.00 | 0.00 | 0.00 | 1.00 |
| Email, llm judge | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| Web page, none | 1.00 | 0.00 | 0.50 | 0.00 | 0.00 | 1.00 |
| Web page, classifier | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| Web page, llm judge | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| File, none | 1.00 | 0.00 | 0.50 | 0.00 | 0.00 | 1.00 |
| File, classifier | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| File, llm judge | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| Tool output, none | 0.50 | 0.00 | 0.50 | 0.00 | 0.00 | 1.00 |
| Tool output, classifier | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| Tool output, llm judge | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 |

: Attack success rate $p_{t,\ell,a}$, false-block rate $r_{t,\ell}$ and normal-task success for each setting.

![Attack success rate by entry point, attack type and guardrail.](figures/payoffs.png){width=95%}

With no guardrail, the most effective attack type was direct override (88% on average), followed by role-play (38%), hidden (12%), split (0%). One check cost 0.58 ms with the classifier and 2.63 s with the LLM judge, measured as wall-clock delay per document read. The judge inspects each segment of a document separately, so its cost is several model calls per read.

## Security versus cost

Table 3 gives the predicted worst-case damage of each policy at the six budget levels. A budget is written as a fraction of what it costs to run the LLM judge on every read. The three fixed baselines do not use the budget: no guardrails costs nothing, and judge everywhere always costs the full amount.

| Budget | GuardEQ | None | Classifier | Judge | Random | Greedy |
|:--|--:|--:|--:|--:|--:|--:|
| 0.0 | 0.80 | 0.80 | 0.40 | 0.00 | 0.80 | 0.80 |
| 0.2 | 0.04 | 0.80 | 0.40 | 0.00 | 0.64 | 0.80 |
| 0.4 | 0.00 | 0.80 | 0.40 | 0.00 | 0.48 | 0.70 |
| 0.6 | 0.00 | 0.80 | 0.40 | 0.00 | 0.32 | 0.60 |
| 0.8 | 0.00 | 0.80 | 0.40 | 0.00 | 0.16 | 0.36 |
| 1.0 | 0.00 | 0.80 | 0.40 | 0.00 | 0.00 | 0.00 |

: Predicted worst-case damage by policy and budget. GuardEQ is the equilibrium policy; Random and Greedy spend the same budget.

![Predicted worst-case damage against budget. Lines are budget-aware policies; dots are the fixed baselines at their own cost.](figures/security_cost.png){width=78%}

**Question 1.** At the 4 intermediate budgets, the equilibrium policy had a strictly lower predicted worst case than random placement at 4 of them and than greedy placement at 4. By construction it can never be worse than either, since both are feasible points of the same linear program. The largest margin was at a budget of 0.2, where the equilibrium's worst case was 0.04 against 0.64 for the better of the two.

**Question 2.** The equilibrium policy reaches the worst-case damage of judge everywhere (0.00) at 24% of its cost. Figure 4 shows how the mix at each entry point changes as the budget grows.

![The equilibrium mix at each entry point, by budget.](figures/policy_mix.png){width=95%}

## Against the LLM attacker

Each policy was run against an LLM attacker (`ollama:gemma4`) that was given the policy, the damage values and the measured success rates. The attacker chose an entry point and an attack type and wrote its own injection text. Tasks came from the held-out templates. Table 4 reports the outcome.

| Policy | Budget | Runs | Success | 95% CI | Damage | Predicted | Gap | Best resp. |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| GuardEQ | 0.25 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| None | 0.25 | 3 | 0.67 | 0.21--0.94 | 0.67 | 0.80 | 0.13 | 0% |
| Classifier | 0.25 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.40 | 0.40 | 33% |
| Judge | 0.25 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| Random | 0.25 | 3 | 0.33 | 0.06--0.79 | 0.33 | 0.60 | 0.27 | 0% |
| Greedy | 0.25 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.80 | 0.80 | 0% |
| GuardEQ | 0.50 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| None | 0.50 | 3 | 0.67 | 0.21--0.94 | 0.67 | 0.80 | 0.13 | 0% |
| Classifier | 0.50 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.40 | 0.40 | 0% |
| Judge | 0.50 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| Random | 0.50 | 3 | 0.33 | 0.06--0.79 | 0.33 | 0.40 | 0.07 | 0% |
| Greedy | 0.50 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.66 | 0.66 | 33% |
| GuardEQ | 0.75 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| None | 0.75 | 3 | 0.67 | 0.21--0.94 | 0.67 | 0.80 | 0.13 | 0% |
| Classifier | 0.75 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.40 | 0.40 | 0% |
| Judge | 0.75 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.00 | 0.00 | 100% |
| Random | 0.75 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.20 | 0.20 | 0% |
| Greedy | 0.75 | 3 | 0.00 | 0.00--0.56 | 0.00 | 0.45 | 0.45 | 0% |

: Each policy against the LLM attacker. Success is the attack success rate, Damage the mean realized damage, Predicted the predicted worst case, and Gap their difference. GuardEQ is the equilibrium policy; Judge and Classifier run that guardrail everywhere.

![Realized damage against the LLM attacker, with 95% intervals. Black marks are the predicted worst case.](figures/eval_damage.png){width=95%}

**Question 3.** Across all 54 runs the attacker gave a usable target in 100% of them and wrote its own payload in 100%. It picked a target that the model identifies as a best response in 37% of runs (100% against the equilibrium policy, where several targets are tied by design). The average shortfall of its chosen target, measured in predicted damage, was 0.223. Realized damage was on average 0.224 below the predicted worst case. A positive gap means the model overstated the risk from this attacker; a negative one means the attacker's own wording did better than the library attacks the payoffs were measured with.

![How often the LLM attacker picked a predicted best response, by policy.](figures/attacker_choice.png){width=70%}

## Robustness

**Question 4.** Table 5 re-solves the game at a budget of 0.5 for different values of $\lambda$. Table 6 scales one damage value at a time. Policy shift is the mean total-variation distance between the new mix and the baseline mix, from 0 (identical) to 1.

| $\lambda$ | Worst-case damage | False-block harm | Cost (s) | Policy shift |
|:--|--:|--:|--:|--:|
| 0.00 | 0.00 | 0.000 | 2.63 | 0.00 |
| 0.25 | 0.00 | 0.000 | 2.63 | 0.00 |
| 0.50 | 0.00 | 0.000 | 2.63 | 0.00 |
| 1.00 | 0.00 | 0.000 | 2.63 | 0.00 |
| 2.00 | 0.00 | 0.000 | 2.63 | 0.00 |

: Sensitivity to the weight on false blocks.

| Entry point | Damage value scaled by | Worst-case damage | Policy shift |
|:--|--:|--:|--:|
| Email | 0.5 | 0.00 | 0.00 |
| Email | 1.5 | 0.00 | 0.00 |
| Web page | 0.5 | 0.00 | 0.00 |
| Web page | 1.5 | 0.00 | 0.00 |
| File | 0.5 | 0.00 | 0.00 |
| File | 1.5 | 0.00 | 0.00 |
| Tool output | 0.5 | 0.00 | 0.00 |
| Tool output | 1.5 | 0.00 | 0.00 |

: Sensitivity to each entry point's damage value.

![Sensitivity of the equilibrium to $\lambda$ and to the damage values.](figures/sensitivity.png){width=90%}

The payoff measurement was repeated with a second model family, `ollama:llama3.2`, at 1 trials per setting. Its normal-task success with no guardrail was 75% and its mean attack success with no guardrail was 44%. The policy solved for `ollama:gemma4` has a predicted worst case of 0.60 when it is evaluated on the second model's payoffs, against 0.07 for the policy solved for that model directly, a transfer penalty of 0.53. The two policies differ by a mean total-variation distance of 0.31.

# Discussion and limitations

The equilibrium policy cannot do worse than random or greedy placement in predicted worst-case damage,
because both are feasible solutions of the program it optimizes. What the experiments can show is how large
the margin is with measured payoffs, and whether the prediction survives contact with an attacker that
writes its own text.

Several limits apply to any reading of the results. The payoffs are estimates from a finite number of
trials, and the linear program treats them as exact; an entry in the payoff table that is zero by chance
makes the solver believe a guardrail is perfect there. The workspace is synthetic and each task reads a
single document, so the traffic weights are parameters of the model and not something the experiments
measure. The classifier is deliberately small. The judge and the agent may be the same model family when
the judge runs locally, which could make the judge better at spotting exactly the text its sibling would
obey. Finally, the attacker is an LLM following a prompt. If it fails to pick the best target, that is a
result about this attacker and this prompt, and a human adversary may do better.

# Reproducing the results

The code is in the `guardeq` package. `python -m guardeq doctor` checks the environment, `python -m unittest`
runs the tests, and `python -m guardeq all --profile full` runs the whole study, resuming from the log if it
is interrupted. `python -m guardeq report` rebuilds this document from the saved results, and `docs/index.html`
is a static page that replays them.

# References

[1] Q. Zhu, "Game Theory Meets LLM and Agentic AI: Reimagining Cybersecurity for the Age of Intelligent Threats," arXiv:2507.10621, 2025.

[2] Z. Han and Q. Zhu, "A Dynamic Stackelberg Game Framework for Agentic AI Defense Against LLM Jailbreaking," arXiv:2507.08207, 2025.

[3] Q. Zhu, "Reasoning and Behavioral Equilibria in LLM-Nash Games: From Mindsets to Actions," arXiv:2507.08208, 2025.

[4] Y. Liu, Y. Jia, J. Jia, D. Song, and N. Z. Gong, "DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks," IEEE Symposium on Security and Privacy, 2025.

[5] J. Pawlick and Q. Zhu, *Game Theory for Cyber Deception: From Theory to Applications*. Springer, 2021.

[6] V. Conitzer and T. Sandholm, "Computing the Optimal Strategy to Commit To," ACM Conference on Electronic Commerce, 2006.

[7] D. Korzhyk, Z. Yin, C. Kiekintveld, V. Conitzer, and M. Tambe, "Stackelberg vs. Nash in Security Games," Journal of Artificial Intelligence Research, 2011.

[8] M. Tambe, *Security and Game Theory: Algorithms, Deployed Systems, Lessons Learned*. Cambridge University Press, 2011.

[9] E. Debenedetti et al., "AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents," NeurIPS Datasets and Benchmarks Track, 2024.

[10] K. Greshake et al., "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection," ACM Workshop on Artificial Intelligence and Security, 2023.
