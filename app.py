# REMOVED eventlet lines to fix the crash
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import logic 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'afghound_cloud_secret'

# CLOUD FIX: Switched to 'gevent' for stability
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', transports=['websocket'], manage_session=False)

# --- GLOBAL STATE ---
global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
player_map = {} 
submitted_data = {} 

@app.route('/')
def index():
    return render_template('index.html')

# --- EMERGENCY RESET BUTTON ---
@app.route('/reset')
def reset_lobby():
    global player_map, submitted_data, global_wallets
    player_map.clear()
    submitted_data.clear()
    global_wallets = {"Afghound": 100, "Player 2": 100, "Player 3": 100}
    socketio.emit('force_refresh', broadcast=True)
    return "<h1>Lobby Reset!</h1><p>All players kicked. <a href='/'>Go Back to Game</a>.</p>"

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    active_roles = list(player_map.values())
    
    # Assign Roles Logic
    if "Afghound" not in active_roles:
        my_role = "Afghound"
    elif "Player 2" not in active_roles:
        my_role = "Player 2"
    elif "Player 3" not in active_roles:
        my_role = "Player 3"
    else:
        my_role = "Spectator"
    
    player_map[sid] = my_role
    emit('assign_role', {'role': my_role, 'wallets': global_wallets})
    emit('lobby_update', {'count': len(player_map), 'players': list(player_map.values())}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in player_map:
        role = player_map.pop(sid)
        if role in submitted_data: del submitted_data[role]
        emit('lobby_update', {'count': len(player_map), 'players': list(player_map.values())}, broadcast=True)

@socketio.on('start_game')
def handle_start():
    if player_map.get(request.sid) != "Afghound": return
    players, s_card, s_holder = logic.setup_game()
    submitted_data.clear()
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
    
    # Check if all CURRENT players are ready
    connected_players = [r for r in player_map.values() if r != "Spectator"]
    if len(submitted_data) >= len(connected_players) and len(submitted_data) > 0:
        logs, wallets = logic.play_showdown(submitted_data, data['straddle'], data['holder'], global_wallets)
        for k, v in wallets.items(): global_wallets[k] = v
        emit('showdown_ready', {"sets": submitted_data, "logs": logs, "wallets": global_wallets}, broadcast=True)
    else:
        emit('status_update', {'ready_count': len(submitted_data), 'total_needed': len(connected_players)}, broadcast=True)

@socketio.on('force_showdown')
def handle_force():
    if player_map.get(request.sid) == "Afghound" and len(submitted_data) > 0:
        logs, wallets = logic.play_showdown(submitted_data, "2H", "None", global_wallets)
        emit('showdown_ready', {"sets": submitted_data, "logs": logs, "wallets": global_wallets}, broadcast=True)

@socketio.on('next_round_trigger')
def handle_next():
    if player_map.get(request.sid) == "Afghound":
        emit('flip_next_row', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)