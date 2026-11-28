"""Expected gag outcomes for the battle UI.

The numbers are the same tables BattleCalculatorAI uses (accuracy, experience
bonus, suit defense, lure bonus, previous-hit bonus, group heal split, drop on
a lured Cog). This module does not roll the hit and does not change battle
state. A result is an estimate, not the outcome the battle will resolve.
"""

MAX_TOON_ACC = 95
ACCURACY_BONUSES = (0, 20, 40, 60)
ATTACK_EXP_PER_TRACK = (0, 10, 20, 30, 40, 50, 60)
BLOCK_INCOMING_SCALE = 0.5

HEAL = 0
TRAP = 1
LURE = 2
SOUND = 3
THROW = 4
SQUIRT = 5
DROP = 6


def block_damage(raw, scale=BLOCK_INCOMING_SCALE):
    """Match BattleBase.blockReducedDamage. A positive hit stays at least 1."""
    try:
        raw = int(raw)
    except (TypeError, ValueError):
        return 0
    if raw <= 0:
        return 0
    reduced = int(raw * scale)
    if reduced < 1:
        reduced = 1
    return reduced


def _clamp_acc(value):
    if value < 0:
        return 0
    if value > MAX_TOON_ACC:
        return MAX_TOON_ACC
    return int(value)


def accuracy(prop_acc, exp_level, suit_def, track,
             all_targets_lured=False, lured_count=0, target_count=1,
             prev_other_hits=0, organic_lure_acc=None):
    """Return the accuracy the calculator compares to random.randint(0, 99).

    Heal on a miss still does 20% in the calculator; this returns the hit chance.
    Trap has no accuracy roll that deals damage. None means 'not an accuracy gag'.
    """
    if track == TRAP:
        return None
    if organic_lure_acc is not None and track == LURE:
        prop_acc = organic_lure_acc
    track_exp = 0
    if 0 <= int(exp_level) < len(ATTACK_EXP_PER_TRACK):
        track_exp = ATTACK_EXP_PER_TRACK[int(exp_level)]
    if track == HEAL:
        track_exp *= 0.5
    defense = 0 if track == HEAL else -int(suit_def or 0)
    acc = prop_acc + track_exp + defense
    bonus_index = prev_other_hits
    if bonus_index < 0:
        bonus_index = 0
    if bonus_index >= len(ACCURACY_BONUSES):
        bonus_index = len(ACCURACY_BONUSES) - 1
    acc += ACCURACY_BONUSES[bonus_index]
    count = target_count if target_count else 1
    if track not in (LURE, HEAL):
        if track != DROP:
            if all_targets_lured and count > 0:
                return 100
            if count > 0 and lured_count > 0:
                acc += 100.0 * (float(lured_count) / float(count))
        elif all_targets_lured and count > 0:
            return 0
    return _clamp_acc(acc)


def split_amount(amount, track, group, target_count):
    """Group heals are divided across eligible Toons. Other amounts are not."""
    if amount is None:
        return None
    if track == HEAL and group and target_count > 1:
        return int(amount / target_count)
    return int(amount)


def gag_tooltip_lines(tbg, track, level, experience, organic, quantity,
                      amount=None, accuracy=None, notes=None):
    group = bool(tbg.isGroup(track, level))
    if notes is None:
        notes = effect_notes(track, level, group, False, False, organic)
        accuracy = tbg.AvLureBonusAccuracy[level] if organic and track == tbg.LURE_TRACK else tbg.AvPropAccuracy[track][level]
        if track != tbg.LURE_TRACK:
            amount = tbg.getAvPropDamage(track, level, experience, organic)
    lines = [str(tbg.AvPropStrings[track][level]).capitalize(),
             '%s · Level %d' % (tbg.Tracks[track], level + 1)]
    if amount is not None:
        lines.append('%s %s' % ('Heal' if track == tbg.HEAL_TRACK else 'Damage', amount))
    if accuracy is not None:
        lines.append('Accuracy %s%%' % accuracy)
    lines.extend(notes[:2])
    lines.append('In bag: %s' % quantity)
    return lines


def effect_notes(track, level, group, lured_targets, trapped_targets, organic):
    notes = []
    if organic:
        notes.append('Organic gag bonus is included.')
    if track == LURE:
        notes.append('Lure lasts for the gag\'s normal round count if it hits.')
    elif track == TRAP:
        notes.append('Trap waits for a lure, then damages that Cog.')
        if lured_targets:
            notes.append('A lured Cog cannot take a trap.')
        if trapped_targets:
            notes.append('A Cog that is already trapped is not a valid trap target.')
    elif track == SOUND:
        if lured_targets:
            notes.append('Sound still damages a lured Cog and knocks it out of lure.')
    elif track == DROP:
        if lured_targets:
            notes.append('Drop deals no damage to a lured Cog.')
    elif track == HEAL:
        if group:
            notes.append('Group heal is split across the other Toons.')
        else:
            notes.append('Heals one Toon.')
    elif group:
        notes.append('Hits every eligible Cog.')
    return notes


def team_summary(entries):
    """Combine already-computed per-gag amounts.

    entries: dicts with keys track, amount, target, group, confirmed, label, lured.
    amount is the per-target value already split for heals. Group attacks pass
    amount as the per-Cog value; combined damage multiplies by the caller's
    target count via `targets` (default 1).
    """
    damage = 0
    heal = 0
    notes = []
    conflicts = []
    traps = {}
    lure_targets = set()
    sound_targets = set()
    drop_targets = set()
    for entry in entries:
        track = entry.get('track')
        amount = entry.get('amount') or 0
        count = entry.get('targets') or 1
        target = entry.get('target')
        if track == HEAL:
            heal += int(amount) * (count if entry.get('group') else 1)
        elif track not in (TRAP, LURE, None):
            if track == DROP and entry.get('lured'):
                notes.append('%s would deal no damage while that Cog is lured.' % entry.get('label', 'Drop'))
            else:
                damage += int(amount) * count
        if track == TRAP and target is not None and not entry.get('group'):
            traps.setdefault(target, []).append(entry.get('label', 'Trap'))
        if track == LURE:
            lure_targets.add(target)
        if track == SOUND:
            sound_targets.add(target)
        if track == DROP:
            drop_targets.add(target)
        if not entry.get('confirmed'):
            notes.append('%s is not confirmed yet.' % entry.get('label', 'A gag'))
    for target, labels in traps.items():
        if len(labels) > 1:
            conflicts.append(('trap-%s' % target, 'More than one trap is aimed at the same Cog.'))
    overlap = (lure_targets & sound_targets) - {None}
    if overlap:
        conflicts.append(('sound-lure', 'Sound knocks a Cog out of lure. Order decides which one lands.'))
    lured_drops = drop_targets & lure_targets
    if any(e.get('track') == DROP and e.get('lured') for e in entries) or lured_drops:
        conflicts.append(('drop-lure', 'Drop does not damage a lured Cog.'))
    if any(e.get('track') == TRAP and e.get('lured') for e in entries):
        conflicts.append(('trap-lure', 'Trap cannot be placed on a lured Cog.'))
    # Same-track attacks share one accuracy roll in the calculator.
    seen = {}
    for entry in entries:
        key = (entry.get('track'), entry.get('target'), entry.get('group'))
        if entry.get('track') in (None, HEAL, TRAP):
            continue
        seen.setdefault(key, []).append(entry.get('label', 'Gag'))
    for labels in seen.values():
        if len(labels) > 1:
            notes.append('Same gag track on one target shares a single accuracy roll.')
            break
    return {
        'damage': damage,
        'heal': heal,
        'notes': notes,
        'conflicts': conflicts,
    }
