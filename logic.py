import random
import sys
import itertools

# =================================================================
# SECTION 1: FOUNDATIONS (Cards and Deck)
# =================================================================

class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
    def __repr__(self):
        readable_ranks = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}
        rank_display = readable_ranks.get(self.rank, str(self.rank))
        return f"{rank_display}{self.suit}"

class Deck:
    def __init__(self):
        self.cards = [Card(s, r) for s in ['♠', '♥', '♦', '♣'] for r in range(2, 15)]
        random.shuffle(self.cards)
    def deal(self, num_cards):
        hand = self.cards[:num_cards]
        self.cards = self.cards[num_cards:]
        return hand

# =================================================================
# SECTION 2: THE SCORING ENGINE (The "Brain")
# =================================================================

def get_set_value(hand):
    """Calculates the strength of a 3-card set (2000-8000+)."""
    sorted_hand = sorted(hand, key=lambda x: x.rank)
    r1, r2, r3 = sorted_hand[0].rank, sorted_hand[1].rank, sorted_hand[2].rank
    s1, s2, s3 = sorted_hand[0].suit, sorted_hand[1].suit, sorted_hand[2].suit
    is_pure = (s1 == s2 == s3)

    if r1 == r2 == r3: return 8000 + r1 # Trio
    if r1 == 2 and r2 == 3 and r3 == 5: return 7000 if is_pure else 5000 # Ramji Special
    
    is_small_straight = (r1 == 2 and r2 == 3 and r3 == 14) # A-2-3
    is_reg_straight = (r2 == r1 + 1 and r3 == r2 + 1)
    if is_small_straight or is_reg_straight:
        base = 6000 if is_pure else 4000
        return base + (13.5 if is_small_straight else r3)
        
    if is_pure: return 3000 + r3 # Flush
    if r1 == r2 or r2 == r3: return 2000 + r2 # Pair
    return 1000 + r3 # High Card

def validate_hand_order(sets):
    """Referees the Strongest-to-Weakest rule."""
    scores = [get_set_value(s) for s in sets]
    for i in range(len(scores) - 1):
        if scores[i] < scores[i+1]: return False, i
    return True, None

# =================================================================
# SECTION 3: COMPETITOR AI (Pattern Hunter)
# =================================================================

def pattern_hunter_ai(hand):
    """AI builds the best possible sets using brute-force search."""
    remaining_cards = list(hand)
    final_sets = []
    for i in range(5):
        best_set, best_val = None, -1
        for combo in itertools.combinations(remaining_cards, 3):
            val = get_set_value(list(combo))
            if val > best_val:
                best_val, best_set = val, list(combo)
        final_sets.append(best_set)
        for card in best_set: remaining_cards.remove(card)
    
    final_sets.sort(key=lambda s: get_set_value(s), reverse=True)
    return final_sets

# =================================================================
# SECTION 4: GAMEPLAY LOGIC (Enhanced for Live Announcements)
# =================================================================

def check_instant_wins(players, straddle_card, straddle_holder):
    """Scans for Quad 4s or Double Quads."""
    for name, hand in players.items():
        counts = {}
        for c in hand: counts[c.rank] = counts.get(c.rank, 0) + 1
        quad_ranks = [r for r, count in counts.items() if count == 4]
        
        if (4 in quad_ranks) or (len(quad_ranks) >= 2):
            reason = "QUAD 4s" if 4 in quad_ranks else "DOUBLE QUADS"
            return True, name, 15
    return False, None, 0

def setup_game():
    """Deals cards, picks Straddle, and determines Remainder pickup."""
    deck = Deck()
    players = {"Afghound": deck.deal(17), "Player 2": deck.deal(17), "Player 3": deck.deal(17)}
    
    all_dealt = players["Afghound"] + players["Player 2"] + players["Player 3"]
    straddle_card = random.choice(all_dealt)
    straddle_holder = next(name for name, hand in players.items() if straddle_card in hand)

    remainder = deck.cards[0]
    house_suit = remainder.suit
    target_rank = 14 if remainder.rank == 2 else 2
    
    # Logic to find who picks up the 18th card
    pickup_found = False
    for name, hand in players.items():
        for card in hand:
            if card.rank == target_rank and card.suit == house_suit:
                hand.append(remainder)
                pickup_found = True; break
        if pickup_found: break
    
    if not pickup_found: players["Afghound"].append(remainder)
    return players, straddle_card, straddle_holder

def play_showdown(all_sets, straddle_card, straddle_holder, wallets):
    """Calculates all results and tags events for live web announcements."""
    win_counts = {"Afghound": 0, "Player 2": 0, "Player 3": 0}
    names = ["Afghound", "Player 2", "Player 3"]
    current_order = ["Afghound", "Player 2", "Player 3"]
    results_log = []

    # Identify Straddle Round
    straddle_round = -1
    for r_idx in range(5):
        if straddle_card in all_sets[straddle_holder][r_idx]:
            straddle_round = r_idx + 1; break
    
    if straddle_round == -1:
        results_log.append(f"EVENT:🚫 STRADDLE MUCKED! {straddle_holder} pays $15 to each.")
        wallets[straddle_holder] -= 30
        for n in names:
            if n != straddle_holder: wallets[n] += 15

    for r in range(1, 6):
        round_sets = {n: all_sets[n][r-1] for n in names}
        scores = {n: get_set_value(round_sets[n]) for n in names}
        
        best_score = max(scores.values())
        winner = next(name for name in reversed(current_order) if scores[name] == best_score)
        win_counts[winner] += 1
        
        # Round Result Line (Website uses this to highlight the winner)
        results_log.append(f"ROUND {r} WINNER: {winner}")
        
        # Basic Round Payout
        for n in wallets:
            wallets[n] += (r * 2) if n == winner else -r

        # Live Straddle Check
        if r == straddle_round:
            if winner == straddle_holder:
                results_log.append(f"EVENT:🎯 STRADDLE SUCCESS! {straddle_holder} wins bonus ${r*2}")
                wallets[straddle_holder] += (r * 2)
                for n in names: 
                    if n != straddle_holder: wallets[n] -= r
            else:
                results_log.append(f"EVENT:🛡️ STRADDLE BROKEN! {straddle_holder} pays ${r} to {winner}")
                wallets[straddle_holder] -= r
                wallets[winner] += r

        # Live Ramji Bonus Check
        for n in names:
            sc = scores[n]
            if (7000 <= sc < 8000) or (5000 <= sc < 6000):
                results_log.append(f"EVENT:✨ RAMJI BONUS! {n} collects ${r*2}")
                wallets[n] += (r*2)
                for other in names: 
                    if other != n: wallets[other] -= r

        # Update turn order for next round
        idx = names.index(winner)
        current_order = names[idx:] + names[:idx]

    # Final Sweep Check
    for n, count in win_counts.items():
        if count == 5:
            results_log.append(f"EVENT:🔥 SWEEP! {n} collects $15 from each.")
            wallets[n]+=30
            for o in wallets: 
                if o != n: wallets[o] -= 15

    return results_log, wallets

# =================================================================
# SECTION 5: EXECUTION (Terminal Support)
# =================================================================

def arrange_sets_manually(hand):
    # (Optional: Terminal helper if you still want to test in console)
    pass

if __name__ == "__main__":
    pass
