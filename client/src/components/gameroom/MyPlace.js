import React from "react";
import TrophySrc from "../../assets/images/1st_trophy.svg";
import { Medium } from "../../styles/font";
import styled from "styled-components";
import BgBox from "../common/BgBox";
//1등 점수 정보
export default function MyPlace({}) {
  const belong = "소속";
  const name = "내이름";
  const score = 7;
  return (
    <BgBox width={"350px"} height={"130px"}>
      <Row>
        <Rank rank={5} />
        <Col>
          <Medium size="45px">{belong}</Medium>

          <Medium size="30px">{name}</Medium>
        </Col>
        <Medium>{score > 0 ? "+" + score : "-" + score}</Medium>
      </Row>
    </BgBox>
  );
}
function Rank({ rank }) {
  return (
    <Circle>
      <Medium color="white" size={"60px"}>
        {rank}
      </Medium>
    </Circle>
  );
}

const Circle = styled.div`
  border-radius: 100%;
  width: 80px;
  height: 80px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: var(--mint);
`;
const Row = styled.div`
  display: flex;
  height: 100%;
  flex-direction: row;
  justify-content: space-around;

  align-items: center;
`;

const Col = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
`;
