import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import logic 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'afghound_cloud_secret'

# CLOUD FIX: manage_session=False prevents cookie confusion between tabs
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', transports=['websocket'], manage_session=False)

# --- GLOBAL STATE ---
global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
player_map = {}      # Maps SID -> Role
submitted_data = {}  # Stores card sets

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/reset')
def reset_lobby():
    """Emergency button to kick everyone and restart server memory"""
    global player_map, submitted_data
    player_map.clear()
    submitted_data.clear()
    socketio.emit('force_refresh', broadcast=True) # Tells all browsers to reload
    return "<h1>Lobby NUKED.</h1><p>All players kicked. <a href='/'>Go back to join as Afghound</a>.</p>"

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    
    # 1. SCOUTING REPORT: Who is currently here?
    active_roles = list(player_map.values())
    
    # 2. ASSIGNMENT LOGIC
    # We enforce strict order: Afghound -> Player 2 -> Player 3
    if "Afghound" not in active_roles:
        my_role = "Afghound"
    elif "Player 2" not in active_roles:
        my_role = "Player 2"
    elif "Player 3" not in active_roles:
        my_role = "Player 3"
    else:
        my_role = "Spectator"
    
    player_map[sid] = my_role
    
    # 3. BROADCAST UPDATES
    emit('assign_role', {'role': my_role, 'wallets': global_wallets})
    emit('lobby_update', {
        'count': len(player_map),
        'players': list(player_map.values()) # Send list of names so we know who is missing
    }, broadcast=True)
    
    print(f"DEBUG: {sid} joined as {my_role}. Active: {list(player_map.values())}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in player_map:
        role = player_map.pop(sid)
        # Clear their submission if they leave so they don't break the game
        if role in submitted_data:
            del submitted_data[role]
        
        print(f"DEBUG: {role} disconnected.")
        emit('lobby_update', {
            'count': len(player_map),
            'players': list(player_map.values())
        }, broadcast=True)

@socketio.on('start_game')
def handle_start():
    if player_map.get(request.sid) != "Afghound": return
    
    players, s_card, s_holder = logic.setup_game()
    submitted_data.clear()
    
    # Deal to whoever is actually connected
    for sid, role in player_map.items():
        if role in players:
            hand = [str(c) for c in sorted(players[role], key=lambda x: x.rank)]
            emit('deal_cards', {
                "hand": hand, "straddle": str(s_card), "holder": s_holder,
                "wallets": global_wallets
            }, room=sid)

@socketio.on('submit_sets')
def handle_submit(data):
    role = player_map.get(request.sid)
    if not role or role == "Spectator": return

    submitted_data[role] = data['sets']
    
    # DYNAMIC THRESHOLD: Proceed if ALL connected players have submitted
    # (This prevents getting stuck if Player 3 is a zombie/missing)
    connected_players = [r for r in player_map.values() if r != "Spectator"]
    players_ready = len(submitted_data)
    total_needed = len(connected_players)
    
    emit('status_update', {
        'ready_count': players_ready, 
        'total_needed': total_needed
    }, broadcast=True)
    
    # If everyone currently in the room is ready, GO!
    if players_ready >= total_needed and players_ready > 0:
        logs, wallets = logic.play_showdown(submitted_data, data['straddle'], data['holder'], global_wallets)
        for k, v in wallets.items(): global_wallets[k] = v
        
        emit('showdown_ready', {
            "sets": submitted_data, "logs": logs, "wallets": global_wallets
        }, broadcast=True)

@socketio.on('force_showdown')
def handle_force():
    """Emergency button for Afghound to force the round if stuck"""
    if player_map.get(request.sid) == "Afghound":
        # Just run with whatever data we have
        if len(submitted_data) > 0:
            logs, wallets = logic.play_showdown(submitted_data, "2H", "None", global_wallets) # dummy straddle
            emit('showdown_ready', {
                "sets": submitted_data, "logs": logs, "wallets": global_wallets
            }, broadcast=True)

@socketio.on('next_round_trigger')
def handle_next():
    if player_map.get(request.sid) == "Afghound":
        emit('flip_next_row', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)