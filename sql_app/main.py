from typing import List, Tuple

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
#from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
#oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

origins = [
    "http://localhost" # TODO 포트 번호 바꾸기
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False, # OAuth 사용 시 True로 바꾸기
    allow_methods=["*"],
    allow_headers=["*"],
)

JSON_SENDING_MODE = "text"
JSON_RECEIVING_MODE = "binary"

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ConnectionManager:
    def __init__(self):
        # Tuple[WebSocket, int, int]: (연결된 웹소켓 클래스, person_id, room_id)
        self.active_connections: List[Tuple[WebSocket, int, int]] = []

    def find_connection_by_websocket(self, websocket: WebSocket):
        return next((x for x in self.active_connections if x[0] == websocket), None)

    def find_connection_by_person_id(self, person_id: int):
        return next((x for x in self.active_connections if x[1] == person_id), None)

    def find_all_connections_by_room_id(self, room_id: int):
        return list(filter(lambda x: x[2] == room_id))

    async def connect(self, websocket: WebSocket, person_id: int, room_id: int):
        await websocket.accept()
        self.active_connections.append((websocket, person_id, room_id))

    def disconnect(self, websocket: WebSocket):
        self.active_connections = list(filter(lambda x: x[0] != websocket, self.active_connections))

    async def close(self, websocket: WebSocket):
        await websocket.close()
        self.disconnect(self, websocket=websocket)

    async def close_with_person_id(self, person_id: int):
        connection = self.find_connection_by_person_id(person_id)
        if connection:
            await connection[0].close()
            self.active_connections.remove(connection)

    async def close_with_room_id(self, room_id: int):
        # 한 방 전체의 사람들을 퇴장시킴
        for connection in self.find_all_connections_by_room_id(room_id):
            await connection[0].close()
            self.active_connections.remove(connection)

    """
    async def send_personal_json(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def send_personal_json_with_person_id(self, message: dict, person_id: int):
        connection = self.find_connection_by_person_id(person_id)
        if connection:
            await connection[0].send_json(message)
    """

    async def send_text(request: str, response: str, message: str, websocket: WebSocket):
        text = {}
        text["request"] = request
        text["response"] = response
        text["type"] = "message"
        text["message"] = message
        await websocket.send_text(text)

    async def send_json(request: str, response: str, type: str, json: dict, websocket: WebSocket):
        json["request"] = request
        json["response"] = response
        json["type"] = type
        await websocket.send_json(json, mode=JSON_SENDING_MODE)

    async def broadcast_json(self, request: str, type: str, json: dict, room_id: int):
        # 한 방 전체의 사람들에게 공통된 JSON을 보냄
        json["request"] = request
        json["response"] = "broadcast"
        json["type"] = type
        for connection in self.find_all_connections_by_room_id(room_id):
            await connection[0].send_json(json, mode=JSON_SENDING_MODE)

manager = ConnectionManager()

@app.websocket("/room")
async def websocket_endpoint(websocket: WebSocket, affiliation: str, name: str, db: Session = Depends(get_db)):
    # 웹소켓 연결 시작
    # 한 번 연결하면 연결을 끊거나 끊어질 때까지 while True:로 모든 데이터를 다 받아야 하나?
    person = crud.get_person_by_affiliation_and_name(db, affiliation=affiliation, name=name)
    if person is None:
        person = crud.create_person(db, affiliation=affiliation, name=name)
    try:
        room = crud.update_last_wait_room_to_enter(db, person.id)
    except Exception as e:
        if str(e.__cause__).find("UNIQUE constraint failed") != -1:
            await websocket.accept()
            await ConnectionManager.send_text("join", "error", "Person already exists in the Room", websocket)
            await websocket.close()
            return
            #raise HTTPException(status_code=400, detail="Person already exists in the Room")
        else:
            await websocket.accept()
            await ConnectionManager.send_text("join", "error", e.__cause__, websocket)
            await websocket.close()
            return
            #raise e
    if room is None:
        await websocket.accept()
        await ConnectionManager.send_text("join", "error", "Person has already entered in non-end Room", websocket)
        await websocket.close()
        return
        #raise HTTPException(status_code=400, detail="Person has already entered in non-end Room")
    game = crud.get_game(db, room.id, person.id)

    connection = manager.find_connection_by_person_id(person.id)
    if connection:
        # 같은 아이디로 중복 접속하는 경우 기존의 사람을 강제로 로그아웃시킴
        await manager.close_with_person_id(person.id)
        
    await manager.connect(websocket, person.id, room.id)
    try:
        # 개인에게 전적('room_id', 'person_id'가 포함된 JSON) 반환 응답
        await ConnectionManager.send_json("join", "success", "game", game, websocket)
        # 해당 방 전체에게 전적(사람) 목록 반환 응답
        await manager.broadcast_json('join', 'game_list', read_game(room.id, db), room.id)
        while True:
            # 클라이언트의 요청 대기
            data = await websocket.receive_json(mode=JSON_RECEIVING_MODE)

            if data["request"] == "hand":
                # 손 입력 요청
                # 해당 방에 새로운 손 추가
                _, error_code = crud.create_hand(db, room_id=room.id, person_id=person.id, hand=data["hand"])
                if error_code == 0:
                    await manager.broadcast_json("hand", "hand_list", read_all_hands(room.id, db), room.id)
                    await manager.broadcast_json("hand", "game_list", read_game(room.id, db), room.id)
                elif error_code == 1 or error_code == 11:
                    await ConnectionManager.send_text("hand", "error", "Room is not in a play mode", websocket)
                    #raise HTTPException(status_code=400, detail="Room is not in a play mode")
                elif error_code == 2 or error_code == 12:
                    await ConnectionManager.send_text("hand", "error", "Game not started yet", websocket)
                    #raise HTTPException(status_code=403, detail="Game not started yet")
                elif error_code == 3 or error_code == 13:
                    await ConnectionManager.send_text("hand", "error", "Person not found", websocket)
                    #raise HTTPException(status_code=404, detail="Person not found")
                elif error_code == 4:
                    await ConnectionManager.send_text("hand", "error", "Initial hand not found", websocket)
                    #raise HTTPException(status_code=500, detail="Initial hand not found")
                elif error_code == 5 or error_code == 15:
                    await ConnectionManager.send_text("hand", "error", "Room not found", websocket)
                    #raise HTTPException(status_code=404, detail="Room not found")
                elif error_code == 6 or error_code == 16:
                    await ConnectionManager.send_text("hand", "error", "Game has ended", websocket)
                    #raise HTTPException(status_code=403, detail="Game has ended")
                    
            elif data["request"] == "quit":
                # 나가기 요청
                # 대기 중인 방일 경우에, 해당 방에 해당 사람이 있으면 제거
                _, error_code = crud.update_room_to_quit(db, room.id, person.id)
                if error_code == 0:
                    await ConnectionManager.send_text("quit", "success", "Successfully signed out", websocket)
                    await manager.close(websocket)
                    await manager.broadcast_json("quit", "game_list", read_game(room.id, db), room.id)
                elif error_code == 1:
                    await ConnectionManager.send_text("quit", "error", "Room not found", websocket)
                    #raise HTTPException(status_code=404, detail="Room not found")
                elif error_code == 2:
                    await ConnectionManager.send_text("quit", "error", "Cannot quit from non-wait Room", websocket)
                    #raise HTTPException(status_code=403, detail="Cannot quit from non-wait Room")
                elif error_code == 3:
                    await ConnectionManager.send_text("quit", "error", "Person not found", websocket)
                    #raise HTTPException(status_code=404, detail="Person not found")
                elif error_code == 4:
                    await ConnectionManager.send_text("quit", "error", "Person does not exist in the Room", websocket)
                    #raise HTTPException(status_code=404, detail="Person does not exist in the Room")
                
            elif data["request"] == "start":
                # 게임 시작 요청

                # 해당 방의 상태 변경
                # 시작 후 time_offset 초 후부터 time_duration 초 동안 손 입력을 받음
                db_room = crud.get_room(db, room.id)
                if db_room is None:
                    await ConnectionManager.send_text("start", "error", "Room not found", websocket)
                    #raise HTTPException(status_code=404, detail="Room not found")

                if db_room.state == schemas.RoomStateEnum.Wait:
                    room = crud.update_room_to_play(db, room_id=room.id, \
                        time_offset=data["time_offset"], time_duration=data["time_duration"])
                else:
                    await ConnectionManager.send_text("start", "error", "Room is not in a wait mode", websocket)
                await manager.broadcast_json("start", "room", db_room, room.id)
                await manager.broadcast_json("start", "hand_list", read_all_hands(room.id, db), room.id)
                await manager.broadcast_json("start", "game_list", read_game(room.id, db), room.id)

            # TODO 게임이 시간이 끝나 종료될 때를 처리해 주어야 함 (각 방마다 확인하면서)
    except WebSocketDisconnect:
        """
        connection = manager.find_connection_by_websocket(websocket)
        if connection:
            room_id = connection[2]
            manager.disconnect(websocket)
            await manager.broadcast_json("disconnected", "game_list", read_game(room_id, db), room_id)
        """
        manager.disconnect(websocket)
        await manager.broadcast_json("disconnected", "game_list", read_game(room.id, db), room.id)

@app.get("/")
def read_root():
    # (디버깅 용도)
    return {"Hello": "World"}

@app.get("/room/list", response_model=List[schemas.Room])
def read_all_room(db: Session = Depends(get_db)):
    # 모든 방 목록 반환 (디버깅 용도)
    rooms = crud.get_rooms(db)
    return rooms

@app.get("/room", response_model=schemas.Room)
def read_or_create_wait_room(db: Session = Depends(get_db)):
    # 대기 중인 방이 있다면 그 방을 반환
    # 없다면 새 대기 방을 만들어 그 방을 반환 (디버깅 용도)
    room = crud.get_last_wait_room(db)
    return room

"""
@app.post("/room", response_model=schemas.Game)
def add_person_to_room(affiliation: str, name: str, db: Session = Depends(get_db)):
    # 회원가입, 로그인, 방 입장을 동시에 처리
    # 대기 중인 방일 경우에, Person 추가하고 해당 방의 인원 수 업데이트
    person = crud.get_person_by_affiliation_and_name(db, affiliation=affiliation, name=name)
    if person is None:
        person = crud.create_person(db, affiliation=affiliation, name=name)
    try:
        room = crud.update_last_wait_room_to_enter(db, person.id)
    except Exception as e:
        if str(e.__cause__).find("UNIQUE constraint failed") != -1:
            raise HTTPException(status_code=400, detail="Person already exists in the Room")
        else:
            raise e
    if room is None:
        raise HTTPException(status_code=400, detail="Person has already entered in non-end Room")
    game = crud.get_game(db, room.id, person.id)

    return game
"""

@app.get("/room/{room_id}")
def read_room(room_id: int, db: Session = Depends(get_db)):
    # 해당 방 반환
    db_room = crud.get_room(db, room_id)
    if db_room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return db_room

@app.delete("/room/{room_id}")
def delete_person_from_room(room_id: int, person_id: int, db: Session = Depends(get_db)):
    # 대기 중인 방일 경우에, 해당 방에 해당 사람이 있으면 제거
    db_room, error_code = crud.update_room_to_quit(db, room_id, person_id)
    if error_code == 0:
        return db_room
    elif error_code == 1:
        raise HTTPException(status_code=404, detail="Room not found")
    elif error_code == 2:
        raise HTTPException(status_code=403, detail="Cannot quit from non-wait Room")
    elif error_code == 3:
        raise HTTPException(status_code=404, detail="Person not found")
    elif error_code == 4:
        raise HTTPException(status_code=404, detail="Person does not exist in the Room")

@app.get("/room/{room_id}/persons")
def read_number_of_persons(room_id: int, db: Session = Depends(get_db)):
    # 해당 방의 사람 수(int) 반환
    db_room = crud.get_room(db, room_id)
    if db_room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    
    return len(db_room.persons)

@app.put("/room/{room_id}/play")
def update_room_to_play(room_id: int, time_offset: int = 5, \
    time_duration: int = 60, db: Session = Depends(get_db)):
    # 해당 방의 상태 변경
    # 시작 후 time_offset 초 후부터 time_duration 초 동안 손 입력을 받음
    db_room = crud.get_room(db, room_id)
    if db_room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if db_room.state == schemas.RoomStateEnum.Wait:
        room = crud.update_room_to_play(db, room_id=room_id, \
            time_offset=time_offset, time_duration=time_duration)
    else:
        raise HTTPException(status_code=400, detail="Room is not in a wait mode")
    return room


@app.put("/room/{room_id}/end")
def update_room_to_end(room_id: int, db: Session = Depends(get_db)):
    # 해당 방의 상태 변경
    # 안에 있는 사람들은 로그아웃 상태(다른 방에 새로 입장할 수 있는 상태)가 됨
    db_room = crud.get_room(db, room_id)
    if db_room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if db_room.state == schemas.RoomStateEnum.Play:
        room = crud.update_room_to_end(db, room_id)
        if room is None:
            raise HTTPException(status_code=403, detail="Game not ended yet")
        else:
            return room
    else:
        raise HTTPException(status_code=400, detail="Room is not in a play mode")

@app.post("/room/{room_id}/hand")
def add_hand(room_id: int, person_id: int, hand: schemas.HandEnum, db: Session = Depends(get_db)):
    # 해당 방에 새로운 손 추가
    db_hand, error_code = crud.create_hand(db, room_id=room_id, person_id=person_id, hand=hand)
    if error_code == 0:
        return db_hand
    elif error_code == 1 or error_code == 11:
        raise HTTPException(status_code=400, detail="Room is not in a play mode")
    elif error_code == 2 or error_code == 12:
        raise HTTPException(status_code=403, detail="Game not started yet")
    elif error_code == 3 or error_code == 13:
        raise HTTPException(status_code=404, detail="Person not found")
    elif error_code == 4:
        raise HTTPException(status_code=500, detail="Initial hand not found")
    elif error_code == 5 or error_code == 15:
        raise HTTPException(status_code=404, detail="Room not found")
    elif error_code == 6 or error_code == 16:
        raise HTTPException(status_code=403, detail="Game has ended")

@app.get("/room/{room_id}/hand")
def read_hands(room_id: int, limit: int = 15, db: Session = Depends(get_db)):
    # 해당 방에서 사람들이 낸 손 목록 limit개 반환 (마지막으로 낸 손이 [0]번째 인덱스)
    hands = crud.get_hands_from_last(db, room_id=room_id, limit=limit)
    ret = []
    for hand in hands:
        person = crud.get_person(db, person_id=hand.person_id)
        ret.append({
            'affiliation': person.affiliation,
            'name': person.name,
            'hand': hand.hand,
            'score': hand.score,
            'time': hand.time,
            'room_id': hand.room_id,
            #'person_id': hand.person_id
        })
    return ret

@app.get("/room/{room_id}/hand/list")
def read_all_hands(room_id: int, db: Session = Depends(get_db)):
    # 해당 방에서 사람들이 낸 손 목록 모두 반환 (마지막으로 낸 손이 [0]번째 인덱스)
    hands = crud.get_hands(db, room_id=room_id)
    ret = []
    for hand in hands:
        person = crud.get_person(db, person_id=hand.person_id)
        ret.append({
            'affiliation': person.affiliation,
            'name': person.name,
            'hand': hand.hand,
            'score': hand.score,
            'time': hand.time,
            'room_id': hand.room_id,
            #'person_id': hand.person_id
        })
    return ret

@app.get("/room/{room_id}/game")
def read_game(room_id: int, db: Session = Depends(get_db)):
    # 해당 방의 사람들의 {순위, 소속, 이름, 점수, win, draw, lose} 반환
    games = crud.get_games_in_room(db, room_id=room_id)
    # 점수가 같다면 이긴 횟수가 많을수록 높은 순위, 이긴 횟수도 같다면 비긴 횟수가 많을수록 높은 순위
    # (많이 낼수록 유리)
    games.sort(key=lambda e: (e.score, e.win, e.draw), reverse=True)
    ret = []
    for index, game in enumerate(games):
        person = crud.get_person(db, person_id=game.person_id)
        ret.append({
            'rank': index + 1, # 순위는 점수가 가장 높은 사람이 1
            'affiliation': person.affiliation,
            'name': person.name,
            'score': game.score,
            'win': game.win,
            'draw': game.draw,
            'lose': game.lose,
            'room_id': game.room_id,
            #'person_id': game.person_id
        })
    return ret

"""
# route 없음
def add_person(affiliation: str, name: str, \
    # hashed_password: str,
    db: Session = Depends(get_db)):
    # 회원가입 겸 로그인: 가입한 사람 목록에 Person 추가
    person = crud.get_person_by_affiliation_and_name(db, affiliation=affiliation, name=name)
    if person is None:
        person = crud.create_person(db, affiliation=affiliation, name=name, \
            #hashed_password=hashed_password,
        )
    return person

@app.get("/person/list")
def read_persons(db: Session = Depends(get_db)):
    # (디버깅 용도)
    return crud.get_persons(db)

@app.get("/person/find")
def read_person_with_affiliation_and_name(affiliation: str, name: str, \
    db: Session = Depends(get_db)):
    # (디버깅 용도)
    person = crud.get_person_by_affiliation_and_name(db, affiliation, name)
    return person

@app.get("/game/list")
def read_all_games(db: Session = Depends(get_db)):
    # (디버깅 용도)
    return crud.get_games(db)
"""