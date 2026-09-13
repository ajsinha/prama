"""SEM-128..SEM-146: MaturityAssessor / EstateFacts / NextAction / MaturityScore cases."""
import sys
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.semantic.maturity import (
    STAGE_WEIGHTS,
    EstateFacts,
    MaturityAssessor,
    MaturityScore,
    MaturityStage,
    NextAction,
)

assessor = MaturityAssessor()

# SEM-128: empty estate
facts = EstateFacts()
score = assessor.assess("estate", facts)
print("SEM-128 completion:", score.completion)
print("SEM-128 score:", score.score, "stage:", score.stage)

# SEM-129: fully described estate
facts = EstateFacts(
    datasets=10, datasets_owned=10, datasets_with_grain=10, datasets_with_rhythm=10,
    datasets_bound=10, attributes=100, attributes_defined=100,
    attributes_mapped_to_concepts=100, tier_one_datasets=2, tier_one_datasets_with_grain=2,
    relationships_confirmed=5, journeys=2, journey_datasets=10,
)
score = assessor.assess("full", facts)
print("SEM-129 score:", score.score, "stage:", score.stage, "actions:", score.actions)

# SEM-130: weights sum to 1.0; RELATED is heaviest
print("SEM-130 sum:", sum(STAGE_WEIGHTS.values()))
print("SEM-130 heaviest:", max(STAGE_WEIGHTS, key=STAGE_WEIGHTS.get), STAGE_WEIGHTS[MaturityStage.RELATED])

# SEM-131: SHAPED = 60% grain + 40% rhythm; 10 datasets all grain, none rhythm
facts = EstateFacts(datasets=10, datasets_with_grain=10, datasets_with_rhythm=0)
completion = facts.stage_completion()
print("SEM-131 SHAPED:", completion[MaturityStage.SHAPED])

# SEM-132: 10 datasets, 5 confirmed relationships -> 1.0; 6 relationships still 1.0
facts5 = EstateFacts(datasets=10, relationships_confirmed=5)
facts6 = EstateFacts(datasets=10, relationships_confirmed=6)
print("SEM-132 with 5:", facts5.stage_completion()[MaturityStage.RELATED])
print("SEM-132 with 6:", facts6.stage_completion()[MaturityStage.RELATED])

# SEM-133: 1 dataset, 0 relationships
facts = EstateFacts(datasets=1, relationships_confirmed=0)
print("SEM-133 RELATED:", facts.stage_completion()[MaturityStage.RELATED])

# SEM-134: stage counts as reached at 80% -- NAMED at 0.80, SHAPED at 0.79
# Build EstateFacts to hit exact completion values, or manipulate directly via _reached_stage
completion = {
    MaturityStage.NAMED: 0.80,
    MaturityStage.SHAPED: 0.79,
    MaturityStage.INTERPRETED: 0.0,
    MaturityStage.RELATED: 0.0,
    MaturityStage.MAPPED: 0.0,
    MaturityStage.JOURNEYED: 0.0,
}
reached = MaturityAssessor._reached_stage(completion)
print("SEM-134 reached:", reached)

# SEM-135: NAMED 1.0, SHAPED 0.2, INTERPRETED 1.0, RELATED 1.0
completion = {
    MaturityStage.NAMED: 1.0,
    MaturityStage.SHAPED: 0.2,
    MaturityStage.INTERPRETED: 1.0,
    MaturityStage.RELATED: 1.0,
    MaturityStage.MAPPED: 0.0,
    MaturityStage.JOURNEYED: 0.0,
}
reached = MaturityAssessor._reached_stage(completion)
print("SEM-135 reached:", reached)

# SEM-136: completion dict missing a key
completion = {MaturityStage.NAMED: 1.0}  # SHAPED etc missing
reached = MaturityAssessor._reached_stage(completion)
print("SEM-136 reached (missing keys):", reached)

# SEM-137: 3 Tier-1 datasets with no grain, 40 other gaps
facts = EstateFacts(
    datasets=43,
    datasets_owned=43,
    datasets_with_grain=0,
    datasets_with_rhythm=0,
    datasets_bound=43,
    attributes=100,
    attributes_defined=0,
    tier_one_datasets=3,
    tier_one_datasets_with_grain=0,
    relationships_confirmed=0,
)
actions = assessor.next_actions(facts)
print("SEM-137 actions[0]:", actions[0].headline, actions[0].estimated_controls, actions[0].value_per_item)

# SEM-138: 10 datasets, 3 tier1, none with grain
facts = EstateFacts(datasets=10, tier_one_datasets=3, tier_one_datasets_with_grain=0, datasets_with_grain=0)
actions = assessor.next_actions(facts)
grain_actions = [a for a in actions if "grain" in a.headline.lower()]
for a in grain_actions:
    print("SEM-138 grain action:", a.headline, "effort_items=", a.effort_items)

# SEM-139: mixed estate producing >= 5 actions, sorted by -value_per_item, effort_items
facts = EstateFacts(
    datasets=40, datasets_owned=30, datasets_with_grain=12, datasets_with_rhythm=8,
    datasets_bound=30, attributes=800, attributes_defined=200,
    attributes_mapped_to_concepts=50, tier_one_datasets=6, tier_one_datasets_with_grain=2,
    relationships_confirmed=3,
)
actions = assessor.next_actions(facts)
print("SEM-139 count:", len(actions))
for a in actions:
    print("  ", a.stage, a.headline, "vpi=", round(a.value_per_item, 3), "effort=", a.effort_items)
is_sorted = all(
    (actions[i].value_per_item, -actions[i].effort_items) >= (actions[i+1].value_per_item, -actions[i+1].effort_items)
    for i in range(len(actions)-1)
)
print("SEM-139 sorted correctly:", is_sorted)

# SEM-140: unbound action
facts = EstateFacts(datasets=10, datasets_bound=5)
actions = assessor.next_actions(facts)
unbound_actions = [a for a in actions if "Connect" in a.headline]
print("SEM-140:", unbound_actions[0].estimated_controls, unbound_actions[0].value_per_item, "is_last:", actions[-1] is unbound_actions[0])

# SEM-141: value_per_item with zero effort
na = NextAction(stage=MaturityStage.SHAPED, headline="h", detail="d", estimated_controls=5, effort_items=0)
print("SEM-141:", na.value_per_item)

# SEM-142: concept-mapping action - 100 attributes, 0 defined, 0 mapped
facts = EstateFacts(datasets=1, attributes=100, attributes_defined=0, attributes_mapped_to_concepts=0)
actions = assessor.next_actions(facts)
mapped_actions = [a for a in actions if a.stage == MaturityStage.MAPPED]
print("SEM-142 mapped actions when 0 defined:", mapped_actions)
# counterfactual: with some defined it should appear
facts2 = EstateFacts(datasets=1, attributes=100, attributes_defined=10, attributes_mapped_to_concepts=0)
actions2 = assessor.next_actions(facts2)
mapped_actions2 = [a for a in actions2 if a.stage == MaturityStage.MAPPED]
print("SEM-142 mapped actions when 10 defined:", [a.headline for a in mapped_actions2])

# SEM-143: explain() lists every component with weight
score = assessor.assess("x", EstateFacts(datasets=2, datasets_owned=1))
lines = score.explain()
print("SEM-143 lines count:", len(lines))
for l in lines:
    print("  ", l)

# SEM-144: pure function - assess twice compare
facts = EstateFacts(datasets=5, datasets_owned=3, attributes=20, attributes_defined=10)
s1 = assessor.assess("x", facts)
s2 = assessor.assess("x", facts)
print("SEM-144 equal score:", s1.score == s2.score, "equal completion:", s1.completion == s2.completion)
print("SEM-144 equal actions:", s1.actions == s2.actions)

# SEM-145: percent rounds
sc1 = MaturityScore(scope="s", facts=EstateFacts(), completion={}, score=0.005, stage=MaturityStage.DISCOVERED, actions=())
sc2 = MaturityScore(scope="s", facts=EstateFacts(), completion={}, score=0.994, stage=MaturityStage.DISCOVERED, actions=())
print("SEM-145:", sc1.percent, sc2.percent)

# SEM-146: control estimates for grain arity - CONTROLS_PER_GRAIN constant value
print("SEM-146 CONTROLS_PER_GRAIN:", MaturityAssessor.CONTROLS_PER_GRAIN)
