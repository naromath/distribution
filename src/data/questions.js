import { generatedQuestionsBank } from './generatedQuestions.js';
import {
  questionReliabilityByQid,
  strictVerifiedQuestionQids,
  goldQuestionQids,
  silverQuestionQids,
  questionReliabilityMeta,
} from './questionReliability.js';

export const subjectsData = [
  {
    name: "유통물류일반",
    color: "badge-blue",
    count: "25문항",
    topics: [
      { name: "유통의 개념과 기능", desc: "유통의 정의, 유통의 사회적 기능(장소·시간·소유 효용 창출), 유통경로의 역할과 중요성", keywords: ["효용 창출", "유통경로", "중간상"] },
      { name: "유통경로의 구조", desc: "유통경로의 유형(직접·간접), 유통경로 길이와 너비, 집약적·선택적·전속적 유통, 도매상과 소매상의 종류", keywords: ["직접유통", "간접유통", "집약적 유통", "전속적 유통"] },
      { name: "물류관리", desc: "물류의 개념과 구성 요소(운송·보관·하역·포장·정보), 물류비 절감 방안, 3PL(제3자 물류)와 4PL", keywords: ["물류 5대 기능", "3PL", "4PL", "물류비"] },
      { name: "공급망관리(SCM)", desc: "SCM의 개념과 목적, 공급망 최적화 전략, 채찍효과(Bullwhip Effect), VMI(공급자 재고관리)", keywords: ["SCM", "채찍효과", "VMI", "JIT"] },
      { name: "재고관리", desc: "재고의 유형과 기능, 경제적 주문량(EOQ), 안전재고, ABC 분석, 재주문점(ROP)", keywords: ["EOQ", "안전재고", "ABC 분석", "ROP"] },
    ]
  },
  {
    name: "상권분석",
    color: "badge-teal",
    count: "25문항",
    topics: [
      { name: "상권의 개념과 유형", desc: "상권의 정의와 범위, 상권의 유형(1차·2차·3차 상권), 상권 형성 요인, 상권과 입지의 차이", keywords: ["1차 상권", "2차 상권", "상권 범위"] },
      { name: "입지이론", desc: "소매인력법칙(레일리), 중심지이론(크리스탈러), 허프모델, 넬슨의 8원칙, 입지 선정 기준", keywords: ["레일리", "허프모델", "넬슨의 원칙", "중심지이론"] },
      { name: "상권조사 기법", desc: "1차·2차 자료 조사, 고객 설문조사, 통행량 조사, 경쟁점 분석, GIS 활용 상권분석", keywords: ["1차 자료", "2차 자료", "통행량", "GIS"] },
      { name: "점포개발과 평가", desc: "점포 입지 평가 기준, 체크리스트 방법, 비교 점수법, 임대료와 매출액 분석, 손익분기점 분석", keywords: ["체크리스트", "비교점수법", "BEP", "임대료"] },
      { name: "소매 유형별 입지 전략", desc: "편의점·슈퍼마켓·백화점·전문점별 최적 입지 기준, 쇼핑센터 개발 전략, 복합쇼핑몰", keywords: ["편의점 입지", "백화점", "쇼핑센터", "복합몰"] },
    ]
  },
  {
    name: "유통마케팅",
    color: "badge-amber",
    count: "25문항",
    topics: [
      { name: "마케팅 전략과 STP", desc: "마케팅의 개념, 시장세분화(Segmentation), 표적시장 선정(Targeting), 포지셔닝(Positioning), 세분화 기준", keywords: ["STP", "시장세분화", "포지셔닝", "표적시장"] },
      { name: "마케팅믹스(4P)", desc: "제품(Product), 가격(Price), 유통(Place), 촉진(Promotion) 전략, 7P(서비스 마케팅), PLC(제품수명주기)", keywords: ["4P", "7P", "PLC", "가격전략"] },
      { name: "판매촉진 전략", desc: "판촉의 종류(광고·인적판매·PR·판매촉진), 쿠폰·샘플링·POP 광고, 푸시·풀 전략 비교", keywords: ["광고", "PR", "쿠폰", "푸시/풀"] },
      { name: "고객관계관리(CRM)", desc: "CRM의 개념과 목적, 고객생애가치(CLV), 고객 충성도 프로그램, 데이터베이스 마케팅", keywords: ["CRM", "CLV", "충성도", "DB마케팅"] },
      { name: "VMD와 머천다이징", desc: "비주얼 머천다이징(VMD)의 개념, 상품진열 기법, 진열 원칙, 카테고리 관리, PB상품 전략", keywords: ["VMD", "진열", "카테고리 관리", "PB상품"] },
    ]
  },
  {
    name: "유통정보",
    color: "badge-coral",
    count: "25문항",
    topics: [
      { name: "유통정보시스템", desc: "유통정보시스템의 구성과 역할, 의사결정지원시스템(DSS), 경영정보시스템(MIS)과 유통 연계", keywords: ["MIS", "DSS", "정보시스템", "의사결정"] },
      { name: "POS 시스템", desc: "POS(판매시점관리) 시스템의 기능과 활용, 데이터 수집과 분석, 재고 연동, POS 데이터 활용 전략", keywords: ["POS", "판매시점", "바코드", "데이터 분석"] },
      { name: "EDI와 전자상거래", desc: "EDI(전자문서교환)의 개념과 장점, 표준화, VAN, e-커머스 유형(B2B·B2C·C2C), 전자결제 수단", keywords: ["EDI", "VAN", "B2B", "B2C", "e-커머스"] },
      { name: "ERP와 통합 시스템", desc: "ERP(전사적 자원관리) 시스템, ERP와 SCM·CRM 연계, WMS(창고관리시스템), TMS(운송관리)", keywords: ["ERP", "WMS", "TMS", "통합시스템"] },
      { name: "바코드·RFID·QR코드", desc: "바코드의 종류(EAN, UPC), RFID의 원리와 장단점, QR코드 활용, IoT와 스마트 유통 기술", keywords: ["EAN", "UPC", "RFID", "QR코드", "IoT"] },
    ]
  }
];

function makeQid(question) {
  return `${question.source}-Q${question.number}`;
}

const strictSet = new Set(strictVerifiedQuestionQids);
const goldSet = new Set(goldQuestionQids);
const silverSet = new Set(silverQuestionQids);

const questionsWithReliability = generatedQuestionsBank.map(question => {
  const qid = makeQid(question);
  const reliability = questionReliabilityByQid[qid] || {
    tier: 'review',
    strictVerified: false,
    score: 0,
    basis: 'unknown',
    frequentMatchCount: 0,
    frequentTopicNumbers: [],
    coreMatchCount: 0,
    corePoints: [],
    noiseFlags: ['no_reliability_data'],
  };

  return {
    ...question,
    qid,
    reliability,
    reliabilityTier: reliability.tier,
    reliabilityScore: reliability.score,
  };
});

const strictQuestionsBank = questionsWithReliability.filter(question => strictSet.has(question.qid));
const goldQuestionsBank = questionsWithReliability.filter(question => goldSet.has(question.qid));
const goldAndSilverQuestionsBank = questionsWithReliability.filter(
  question => goldSet.has(question.qid) || silverSet.has(question.qid)
);
const selectedQuestionsBank = questionsWithReliability;
const selectedMode = 'all_verified';

export const questionsBank = [...selectedQuestionsBank];
export const questionsBankMeta = {
  selectedMode,
  manualVerifiedAll: true,
  selectedCount: selectedQuestionsBank.length,
  strictCount: strictQuestionsBank.length,
  goldCount: goldQuestionsBank.length,
  goldSilverCount: goldAndSilverQuestionsBank.length,
  totalCount: questionsWithReliability.length,
  reliability: questionReliabilityMeta,
};
