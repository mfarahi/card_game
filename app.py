import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import logic 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'afghound_cloud_secret'

# Cloud Fix: Force WebSocket only
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', transports=['websocket'])

# --- GLOBAL STATE ---
global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
player_map = {} 
submitted_data = {} 

@app.route('/')
def index():
    return render_template('index.html')

# --- NEW: EMERGENCY RESET BUTTON ---
@app.route('/reset')
def reset_lobby():
    global player_map, submitted_data, global_wallets
    player_map.clear()
    submitted_data.clear()
    # Optional: Reset wallets too, or keep them. Here we reset them to be safe.
    global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
    print("DEBUG: Lobby has been forcibly reset.")
    return "<h1>Lobby Reset!</h1><p>All players have been kicked. You can now <a href='/'>Go Back to Game</a> and be Afghound.</p>"

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    
    # SMART SLOT FILLING:
    # Instead of just counting, we check exactly which seats are empty.
    active_roles = list(player_map.values())
    possible_roles = ["Afghound", "Player 2", "Player 3"]
    
    # Find the first role that is NOT currently taken
    assigned_role = None
    for r in possible_roles:
        if r not in active_roles:
            assigned_role = r
            break
    
    if assigned_role:
        player_map[sid] = assigned_role
        emit('assign_role', {'role': assigned_role, 'wallets': global_wallets})
        emit('lobby_update', {'count': len(player_map)}, broadcast=True)
        print(f"DEBUG: {sid} joined as {assigned_role}")
    else:
        # Room is full
        emit('assign_role', {'role': 'Spectator', 'wallets': global_wallets})
        print(f"DEBUG: {sid} joined as Spectator (Room Full)")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in player_map:
        role = player_map.pop(sid)
        print(f"DEBUG: {role} disconnected.")
        emit('lobby_update', {'count': len(player_map)}, broadcast=True)

@socketio.on('start_game')
def handle_start():
    # Only Afghound can start, but double check they exist
    if player_map.get(request.sid) != "Afghound": return
    
    if any(v <= 0 for v in global_wallets.values()):
        emit('player_bankrupt', {'wallets': global_wallets}, broadcast=True)
        return

    players, s_card, s_holder = logic.setup_game()
    submitted_data.clear()
    
    for sid, role in player_map.items():
        if role in ["Afghound", "Player 2", "Player 3"]:
            hand = [str(c) for c in sorted(players[role], key=lambda x: x.rank)]
            emit('deal_cards', {
                "hand": hand, "straddle": str(s_card), "holder": s_holder,
                "wallets": global_wallets
            }, room=sid)

@socketio.on('submit_sets')
def handle_submit(data):
    role = player_map.get(request.sid)
    if role:
        submitted_data[role] = data['sets']
        emit('status_update', {'ready_count': len(submitted_data)}, broadcast=True)
        
        if len(submitted_data) == 3:
            logs, wallets = logic.play_showdown(submitted_data, data['straddle'], data['holder'], global_wallets)
            for k, v in wallets.items(): global_wallets[k] = v
            emit('showdown_ready', {"sets": submitted_data, "logs": logs, "wallets": global_wallets}, broadcast=True)

@socketio.on('next_round_trigger')
def handle_next():
    if player_map.get(request.sid) == "Afghound":
        emit('flip_next_row', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)