import React, { useState, useEffect } from "react";
import styled from "styled-components";
import Room from "./Room";
import GradientBtn from "./GradientBtn";
import SizedBox from "../common/SizedBox";
import { Language } from "../../db/Language";
import { LanguageContext } from "../../utils/LanguageProvider";
import { useContext } from "react";
import RefreshBtn from "./RefreshBtn";
import { WebsocketContext } from "../../utils/WebSocketProvider";
function RoomList({ rooms, setCreateRoomModalVisible }) {
  const mode = useContext(LanguageContext);

  const [roomLists, setRoomLists] = useState(rooms);

  const [createSocketConnection, ready, ws] = useContext(WebsocketContext); //전역 소켓 불러오기
  useEffect(() => {
    ws.onmessage = function (event) {
      const res = JSON.parse(event.data);

      if (ready) {
        if (res?.response === "error") {
          alert(res.message);
          return;
        }

        switch (res?.type) {
          case "room_list": // 룸 목록 갱신 요청에 대한 응답
            setRoomLists(res.data);
        }
      }
    };
  }, [ready]);
  const _openCreateRoomModal = () => {
    setCreateRoomModalVisible(true);
  };

  const _quickStart = () => {
    // console.log("quick start success");
  };

  const blueBtnStyle = {
    width: "130px",
    height: "40px",
    borderRadius: "10px",
    bg: "linear-gradient(180deg, #3AB6BC 0%, #3A66BC 100%, #2F508E 100%);",
  };
  const redBtnStyle = {
    width: "130px",
    height: "40px",
    borderRadius: "10px",
    bg: "linear-gradient(180deg, #FA1515 0%, #F97916 100%);",
  };

  const _refreshRoomList = () => {
    if (ready) {
      let request = {
        request: "refresh",
      };
      ws.send(JSON.stringify(request));
    }
  };
  return (
    <BgBox>
      <Row>
        <div style={{ display: "flex", flexDirection: "row", gap: "30px" }}>
          <GradientBtn
            text={Language[mode].create_room}
            onClick={_openCreateRoomModal}
            style={blueBtnStyle}
            anim
          />

          <GradientBtn
            text={Language[mode].quick_start}
            onClick={_quickStart}
            style={redBtnStyle}
            anim
          />
        </div>
        <RefreshBtn onClick={_refreshRoomList} />
      </Row>
      <SizedBox width="100%" height={"30px"} />
      <RoomContainer>
        {roomLists.map((room) => (
          <Room room={room} />
        ))}
      </RoomContainer>
    </BgBox>
  );
}

const BgBox = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  flex-wrap: wrap;

  align-self: center;
  margin: auto;
  margin-top: 5%;
  background: rgba(123, 120, 213, 0.22);

  width: 50%;
  height: 500px;
  padding: 40px;
  border-radius: 10px;
`;

const RoomContainer = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  flex-wrap: wrap;
  width: 100%;
  height: 90%;
  overflow-y: auto;
  padding-right: 15px;
  grid-gap: 30px 20px;
  ::-webkit-scrollbar {
    width: 15px; /* 스크롤바의 너비 */
  }

  ::-webkit-scrollbar-thumb {
    background: #f5f5f5; /* 스크롤바의 색상 */

    border-radius: 10px;
  }

  ::-webkit-scrollbar-track {
    background: rgba(33, 122, 244, 0.1); /*스크롤바 뒷 배경 색상*/
  }
`;

const Row = styled.div`
  width: 100%;
  display: flex;
  flex-direction: row;
  justify-content: space-between;

  gap: 20px;
`;
export default RoomList;
