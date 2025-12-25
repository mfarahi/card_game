import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import logic 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'afghound_cloud_secret'

# CLOUD FIX: Force WebSocket only to prevent "GET /" refresh loops
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', transports=['websocket'])

# --- LOCKED GLOBAL STATE ---
global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
connected_sids = [] 
player_map = {} 
submitted_data = {} 

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    # Cloud Logic: Assign roles strictly by join order
    if sid not in connected_sids and len(connected_sids) < 3:
        connected_sids.append(sid)
        roles = ["Afghound", "Player 2", "Player 3"]
        role = roles[len(connected_sids) - 1]
        player_map[sid] = role
        
        # Send role and current wallet state immediately
        emit('assign_role', {'role': role, 'wallets': global_wallets})
        emit('lobby_update', {'count': len(connected_sids)}, broadcast=True)
        print(f"DEBUG: {role} connected via WebSocket.")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in connected_sids:
        connected_sids.remove(sid)
        if sid in player_map: del player_map[sid]
        emit('lobby_update', {'count': len(connected_sids)}, broadcast=True)

@socketio.on('start_game')
def handle_start():
    if player_map.get(request.sid) != "Afghound": return
    
    # Bankruptcy Guard
    if any(v <= 0 for v in global_wallets.values()):
        emit('player_bankrupt', {'wallets': global_wallets}, broadcast=True)
        return

    players, s_card, s_holder = logic.setup_game()
    submitted_data.clear()
    
    for sid, role in player_map.items():
        # Sort hand for display
        hand = [str(c) for c in sorted(players[role], key=lambda x: x.rank)]
        emit('deal_cards', {
            "hand": hand, "straddle": str(s_card), "holder": s_holder,
            "wallets": global_wallets
        }, room=sid)

@socketio.on('submit_sets')
def handle_submit(data):
    role = player_map.get(request.sid)
    submitted_data[role] = data['sets']
    
    # Barrier Logic: Update count but do NOT reveal
    emit('status_update', {'ready_count': len(submitted_data)}, broadcast=True)
    
    if len(submitted_data) == 3:
        logs, wallets = logic.play_showdown(submitted_data, data['straddle'], data['holder'], global_wallets)
        for k, v in wallets.items(): global_wallets[k] = v
        
        # Broadcast full results only when everyone is ready
        emit('showdown_ready', {
            "sets": submitted_data, "logs": logs, "wallets": global_wallets
        }, broadcast=True)

@socketio.on('next_round_trigger')
def handle_next():
    if player_map.get(request.sid) == "Afghound":
        emit('flip_next_row', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)