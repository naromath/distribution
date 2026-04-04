import './style.css';
import { subjectsData, questionsBank, questionsBankMeta } from './data/questions.js';
import { coreSummaryBySubject, frequent100Topics } from './data/learningAssets.js';

const SUBJECT_ORDER = ['유통물류일반', '상권분석', '유통마케팅', '유통정보'];
const PROGRESS_VERSION = 1;
const ANSWER_HISTORY_LIMIT = 8000;
const QUIZ_HISTORY_LIMIT = 500;
const TARGET_SECONDS_PER_QUESTION = 67;
const ERROR_TYPE_OPTIONS = [
  { key: 'concept', label: '개념 부족형' },
  { key: 'confusion', label: '헷갈림형' },
  { key: 'memory', label: '암기 부족형' },
  { key: 'trap', label: '문장 함정형' },
];
const ERROR_TYPE_LABEL_MAP = Object.fromEntries(
  ERROR_TYPE_OPTIONS.map(option => [option.key, option.label])
);
const TRAP_WORDS = ['항상', '반드시', '전부', '예외없이', '절대', '오직', '즉시', '모든'];
const MEMORY_PATTERN = /(순서|절차|기간|비율|횟수|기준|기관|등록|신고|비용|점수|\d)/;

let currentUserId = null;
let currentQuizList = [];
let currentQIndex = 0;
let score = 0;
let currentQuizMode = 'normal';
let currentQuizStartedAt = null;
let currentQuestionStartedAt = null;
let currentQuizContext = { subject: '전체 과목', requestedCount: 10 };
let currentQuizAnswerLog = [];
let isLoginMode = true;


function renderQuestionBankSummary() {
  const element = document.getElementById('bank-quality-summary');
  if (!element) return;

  if (questionsBankMeta.manualVerifiedAll) {
    element.textContent = `문제은행 ${questionsBankMeta.selectedCount}문항 · 전수검증 완료 · 전체 사용`;
    return;
  }

  const modeMap = {
    all_verified: '전체 사용(전수검증 완료)',
    strict: 'Strict(완전매치)',
    gold_silver_auto: 'Gold+Silver(자동)',
    all_fallback: '전체 fallback',
  };

  const selectedMode = modeMap[questionsBankMeta.selectedMode] || questionsBankMeta.selectedMode;
  const strictCount = Number(questionsBankMeta.strictCount || 0);
  const rel = questionsBankMeta.reliability?.tierCounts || {};
  const goldCount = Number(rel.gold || 0);
  const silverCount = Number(rel.silver || 0);
  const reviewCount = Number(rel.review || 0);

  element.textContent =
    `문제은행 ${questionsBankMeta.selectedCount}문항 · 모드 ${selectedMode} · Strict ${strictCount} / Gold ${goldCount} / Silver ${silverCount} / Review ${reviewCount}`;
}

function normalizeForMatch(text) {
  return String(text ?? '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[^0-9a-z가-힣]/g, '');
}

function buildFrequentTopicMatchers() {
  return frequent100Topics.map(topic => {
    const keywordEntries = (topic.keywords || [])
      .map(raw => String(raw).trim())
      .filter(Boolean)
      .map(raw => ({ raw, normalized: normalizeForMatch(raw) }))
      .filter(({ raw, normalized }) => {
        if (!normalized) return false;
        if (normalized.length >= 3) return true;
        return /^[a-z0-9]{2,}$/i.test(raw);
      });

    const normalizedKeywords = [...new Set(keywordEntries.map(entry => entry.normalized))];
    return {
      number: topic.number,
      title: topic.title,
      normalizedKeywords,
    };
  });
}

const frequentTopicMatchers = buildFrequentTopicMatchers();

function enrichQuestion(question) {
  const normalizedQuestion = normalizeForMatch(
    `${question.question} ${(question.options || []).join(' ')}`
  );

  const matchedTopics = [];
  let frequentScore = 0;

  frequentTopicMatchers.forEach(topic => {
    const matched = topic.normalizedKeywords.some(keyword => normalizedQuestion.includes(keyword));
    if (matched) {
      matchedTopics.push(topic.title);
      frequentScore += 1;
    }
  });

  return {
    ...question,
    qid: `${question.source}-Q${question.number}`,
    frequentScore,
    frequentTags: matchedTopics.slice(0, 3),
  };
}

const enrichedQuestionsBank = questionsBank.map(enrichQuestion);
const questionByQid = new Map(enrichedQuestionsBank.map(question => [question.qid, question]));
const frequentQuestionQids = new Set(
  enrichedQuestionsBank.filter(question => question.frequentScore > 0).map(question => question.qid)
);

function sortByFrequentPriority(items) {
  return [...items].sort((a, b) => {
    if (b.frequentScore !== a.frequentScore) return b.frequentScore - a.frequentScore;
    if (a.subject !== b.subject) return SUBJECT_ORDER.indexOf(a.subject) - SUBJECT_ORDER.indexOf(b.subject);
    if (a.source !== b.source) return String(a.source).localeCompare(String(b.source));
    return Number(a.number) - Number(b.number);
  });
}

function filterQuestionsBySubject(items, subject) {
  if (subject === '전체 과목') return [...items];
  return items.filter(item => item.subject === subject);
}

function uniqueByQid(items) {
  const seen = new Set();
  const unique = [];
  items.forEach(item => {
    if (!seen.has(item.qid)) {
      seen.add(item.qid);
      unique.push(item);
    }
  });
  return unique;
}

function buildFrequentTwentySet(pool, selectedSubject) {
  const frequentPool = pool.filter(item => item.frequentScore > 0);
  const basePool = frequentPool.length > 0 ? frequentPool : pool;
  const ranked = sortByFrequentPriority(basePool);

  if (selectedSubject !== '전체 과목') {
    return ranked.slice(0, 20);
  }

  const picked = [];
  const pickedIds = new Set();

  SUBJECT_ORDER.forEach(subject => {
    const perSubject = ranked.filter(item => item.subject === subject).slice(0, 5);
    perSubject.forEach(item => {
      if (!pickedIds.has(item.qid) && picked.length < 20) {
        picked.push(item);
        pickedIds.add(item.qid);
      }
    });
  });

  ranked.forEach(item => {
    if (picked.length >= 20) return;
    if (!pickedIds.has(item.qid)) {
      picked.push(item);
      pickedIds.add(item.qid);
    }
  });

  if (picked.length < 20) {
    sortByFrequentPriority(pool).forEach(item => {
      if (picked.length >= 20) return;
      if (!pickedIds.has(item.qid)) {
        picked.push(item);
        pickedIds.add(item.qid);
      }
    });
  }

  return picked.slice(0, 20);
}

function getQuizModeLabel(mode) {
  if (mode === 'frequent-priority') return '빈출 우선';
  if (mode === 'frequent-20') return '빈출 20세트';
  if (mode === 'wrong-note') return '오답 집중 복습';
  if (mode === 'auto-cycle') return '회독 자동 모드';
  return '일반 랜덤';
}

function createRecordId(prefix = 'id') {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function detectTrapWords(text) {
  const normalized = normalizeForMatch(text);
  return TRAP_WORDS.filter(word => normalized.includes(normalizeForMatch(word)));
}

function getErrorTypeLabel(type) {
  return ERROR_TYPE_LABEL_MAP[type] || '-';
}

function getProgressStorageKey(userId) {
  return `progress_${userId}`;
}

function emptyProgressState() {
  return {
    version: PROGRESS_VERSION,
    answers: [],
    quizzes: [],
  };
}

function loadProgressState() {
  if (!currentUserId) return emptyProgressState();
  const key = getProgressStorageKey(currentUserId);
  const raw = localStorage.getItem(key);
  if (!raw) return emptyProgressState();

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return emptyProgressState();
    const answers = Array.isArray(parsed.answers) ? parsed.answers : [];
    const quizzes = Array.isArray(parsed.quizzes) ? parsed.quizzes : [];
    return {
      version: PROGRESS_VERSION,
      answers,
      quizzes,
    };
  } catch (error) {
    return emptyProgressState();
  }
}

function saveProgressState(state) {
  if (!currentUserId) return;
  const key = getProgressStorageKey(currentUserId);
  localStorage.setItem(key, JSON.stringify(state));
}

function appendAnswerRecord(record) {
  if (!currentUserId) return null;
  const state = loadProgressState();
  const entry = {
    id: record.id || createRecordId('ans'),
    ...record,
  };
  state.answers.push(entry);
  if (state.answers.length > ANSWER_HISTORY_LIMIT) {
    state.answers = state.answers.slice(-ANSWER_HISTORY_LIMIT);
  }
  saveProgressState(state);
  return entry.id;
}

function updateAnswerRecord(answerId, patch) {
  if (!currentUserId || !answerId) return;
  const state = loadProgressState();
  const index = state.answers.findIndex(answer => answer.id === answerId);
  if (index === -1) return;
  state.answers[index] = {
    ...state.answers[index],
    ...patch,
  };
  saveProgressState(state);
}

function updateCurrentQuizAnswerLog(answerId, patch) {
  const index = currentQuizAnswerLog.findIndex(answer => answer.id === answerId);
  if (index === -1) return;
  currentQuizAnswerLog[index] = {
    ...currentQuizAnswerLog[index],
    ...patch,
  };
}

function appendQuizRecord(record) {
  if (!currentUserId) return;
  const state = loadProgressState();
  state.quizzes.push(record);
  if (state.quizzes.length > QUIZ_HISTORY_LIMIT) {
    state.quizzes = state.quizzes.slice(-QUIZ_HISTORY_LIMIT);
  }
  saveProgressState(state);
}

function safeRate(correct, total) {
  if (!total) return 0;
  return Math.round((correct / total) * 100);
}

function computeAccuracy(records) {
  const total = records.length;
  const correct = records.filter(record => record.correct).length;
  return {
    total,
    correct,
    rate: safeRate(correct, total),
  };
}

function getRecent(records, count) {
  if (records.length <= count) return [...records];
  return records.slice(records.length - count);
}

function getLocalDateKey(timestamp) {
  const date = new Date(timestamp);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function computeSubjectStats(answers, limitPerSubject = 50) {
  return SUBJECT_ORDER.map(subject => {
    const subjectAnswers = answers.filter(answer => answer.subject === subject);
    const recentSubjectAnswers = getRecent(subjectAnswers, limitPerSubject);
    const accuracy = computeAccuracy(recentSubjectAnswers);
    return {
      subject,
      total: accuracy.total,
      correct: accuracy.correct,
      rate: accuracy.rate,
    };
  });
}

function computeFrequentProgress(answers) {
  const frequentAnswers = answers.filter(answer => Number(answer.frequentScore || 0) > 0);
  const uniqueSolved = new Set(frequentAnswers.map(answer => answer.qid)).size;
  const accuracy = computeAccuracy(frequentAnswers);
  const totalFrequentQuestions = frequentQuestionQids.size;

  return {
    totalFrequentQuestions,
    solvedUnique: uniqueSolved,
    progressRate: safeRate(uniqueSolved, totalFrequentQuestions),
    accuracy,
  };
}

function computeRecoveryRate(answers) {
  const tracker = new Map();
  answers.forEach(answer => {
    const previous = tracker.get(answer.qid) || { hadWrong: false, recovered: false };
    if (!answer.correct) {
      previous.hadWrong = true;
    } else if (previous.hadWrong) {
      previous.recovered = true;
    }
    tracker.set(answer.qid, previous);
  });

  let wrongQuestionCount = 0;
  let recoveredQuestionCount = 0;
  tracker.forEach(state => {
    if (state.hadWrong) {
      wrongQuestionCount += 1;
      if (state.recovered) recoveredQuestionCount += 1;
    }
  });

  return {
    wrongQuestionCount,
    recoveredQuestionCount,
    rate: wrongQuestionCount > 0 ? safeRate(recoveredQuestionCount, wrongQuestionCount) : null,
  };
}

function computePace(answers) {
  const withElapsed = answers.filter(
    answer => Number.isFinite(answer.elapsedSec) && answer.elapsedSec > 0
  );
  const recent = getRecent(withElapsed, 200);
  if (recent.length === 0) {
    return { avgSec: null, count: 0, status: '데이터 없음' };
  }
  const avg = recent.reduce((sum, answer) => sum + answer.elapsedSec, 0) / recent.length;
  const rounded = Math.round(avg);
  let status = '적정';
  if (rounded <= 60) status = '빠름';
  if (rounded > 75) status = '느림';
  return { avgSec: rounded, count: recent.length, status };
}

function computeReadiness(answers, quizzes, subjectStats) {
  if (answers.length < 20) {
    return {
      label: '데이터 부족',
      detail: '최소 20문항 이상 풀이 시 합격 예측 정확도가 올라갑니다.',
    };
  }

  const recent100 = computeAccuracy(getRecent(answers, 100));
  const recent5Quizzes = getRecent(quizzes, 5);
  const recentQuizAvg = recent5Quizzes.length
    ? Math.round(
        recent5Quizzes.reduce((sum, quiz) => sum + Number(quiz.percent || 0), 0) / recent5Quizzes.length
      )
    : null;

  const trackedSubjects = subjectStats.filter(stat => stat.total >= 5);
  const allTracked = trackedSubjects.length === SUBJECT_ORDER.length;
  const hasUnder40 = trackedSubjects.some(stat => stat.rate < 40);

  let label = '주의';
  if (allTracked && recent100.rate >= 60 && !hasUnder40) label = '합격권';
  if (hasUnder40 || recent100.rate < 50) label = '위험';

  const quizPart = recentQuizAvg === null ? '최근 모의 데이터 없음' : `최근 5회 ${recentQuizAvg}%`;
  const subjectPart = allTracked
    ? `최저 과목 ${Math.min(...trackedSubjects.map(stat => stat.rate))}%`
    : '과목별 데이터 수집 중';

  return {
    label,
    detail: `최근 100문항 ${recent100.rate}% · ${quizPart} · ${subjectPart}`,
  };
}

function computeWeeklyTrend(answers) {
  const map = new Map();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const keys = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - offset);
    const key = getLocalDateKey(date.getTime());
    keys.push(key);
    map.set(key, { total: 0, correct: 0 });
  }

  answers.forEach(answer => {
    const key = getLocalDateKey(answer.ts);
    if (!map.has(key)) return;
    const day = map.get(key);
    day.total += 1;
    if (answer.correct) day.correct += 1;
    map.set(key, day);
  });

  return keys.map(key => {
    const value = map.get(key);
    const date = new Date(`${key}T00:00:00`);
    const label = `${date.getMonth() + 1}/${date.getDate()}`;
    return {
      key,
      label,
      total: value.total,
      correct: value.correct,
      rate: safeRate(value.correct, value.total),
    };
  });
}

function computeQuestionLearningState(answers) {
  const states = new Map();
  answers.forEach(answer => {
    const prev = states.get(answer.qid) || {
      qid: answer.qid,
      wrongCount: 0,
      correctCount: 0,
      correctStreak: 0,
      lastWrongTs: null,
      lastCorrectTs: null,
      lastCorrect: false,
      errorTypeCounts: {},
    };

    if (answer.correct) {
      prev.correctCount += 1;
      prev.correctStreak += 1;
      prev.lastCorrectTs = answer.ts;
      prev.lastCorrect = true;
    } else {
      prev.wrongCount += 1;
      prev.correctStreak = 0;
      prev.lastWrongTs = answer.ts;
      prev.lastCorrect = false;
      if (answer.errorType) {
        prev.errorTypeCounts[answer.errorType] = (prev.errorTypeCounts[answer.errorType] || 0) + 1;
      }
    }

    prev.isMastered = prev.correctStreak >= 2;
    prev.needsReview = prev.wrongCount > 0 && !prev.isMastered;
    states.set(answer.qid, prev);
  });
  return states;
}

function buildWrongNoteSet(pool, count, learningStates) {
  const unresolved = pool.filter(question => {
    const state = learningStates.get(question.qid);
    return state && state.needsReview;
  });

  if (unresolved.length > 0) {
    return [...unresolved]
      .sort((a, b) => {
        const stateA = learningStates.get(a.qid);
        const stateB = learningStates.get(b.qid);
        const wrongDiff = (stateB?.wrongCount || 0) - (stateA?.wrongCount || 0);
        if (wrongDiff !== 0) return wrongDiff;
        return (stateB?.lastWrongTs || 0) - (stateA?.lastWrongTs || 0);
      })
      .slice(0, count);
  }

  const allWrong = pool.filter(question => {
    const state = learningStates.get(question.qid);
    return state && state.wrongCount > 0;
  });
  if (allWrong.length > 0) {
    return sortByFrequentPriority(allWrong).slice(0, count);
  }
  return [];
}

function buildAutoCycleSet(pool, count, state, subject) {
  const answers = state.answers || [];
  const learningStates = computeQuestionLearningState(answers);
  const wrongSet = buildWrongNoteSet(pool, count, learningStates);
  const frequentSet = sortByFrequentPriority(pool.filter(question => question.frequentScore > 0));

  if (answers.length < 150) {
    return {
      stage: '1회독',
      items: shuffleArray(pool).slice(0, count),
    };
  }
  if (wrongSet.length >= Math.min(15, count)) {
    return {
      stage: '2회독',
      items: wrongSet.slice(0, count),
    };
  }
  if (frequentSet.length > 0) {
    return {
      stage: '3회독',
      items: frequentSet.slice(0, count),
    };
  }

  const stage4Items =
    subject === '전체 과목'
      ? buildFrequentTwentySet(pool, subject).slice(0, count)
      : shuffleArray(pool).slice(0, count);

  return {
    stage: '4회독',
    items: stage4Items,
  };
}

function computeDailyRoutine(answers) {
  const todayKey = getLocalDateKey(Date.now());
  const todayAnswers = answers.filter(answer => getLocalDateKey(answer.ts) === todayKey);
  const solvedCount = todayAnswers.length;
  const classifiedWrongCount = todayAnswers.filter(
    answer => !answer.correct && Boolean(answer.errorType)
  ).length;

  const seenWrong = new Set();
  let recoveredCount = 0;
  answers.forEach(answer => {
    const isToday = getLocalDateKey(answer.ts) === todayKey;
    if (answer.correct && isToday && seenWrong.has(answer.qid)) {
      recoveredCount += 1;
    }
    if (!answer.correct) seenWrong.add(answer.qid);
  });

  return [
    {
      key: 'solve',
      title: '1교시: 기출 20~30문항 풀이',
      current: solvedCount,
      target: 30,
      unit: '문항',
    },
    {
      key: 'classify',
      title: '2교시: 오답 유형 분류',
      current: classifiedWrongCount,
      target: 10,
      unit: '문항',
    },
    {
      key: 'recover',
      title: '3교시: 전날 오답 재도전',
      current: recoveredCount,
      target: 10,
      unit: '문항',
    },
  ];
}

function computeErrorTypeStats(answers) {
  const wrongAnswers = getRecent(answers.filter(answer => !answer.correct), 300);
  const counts = Object.fromEntries(ERROR_TYPE_OPTIONS.map(option => [option.key, 0]));
  let unclassified = 0;

  wrongAnswers.forEach(answer => {
    if (answer.errorType && counts[answer.errorType] !== undefined) {
      counts[answer.errorType] += 1;
    } else {
      unclassified += 1;
    }
  });

  return {
    totalWrong: wrongAnswers.length,
    counts,
    unclassified,
  };
}

function computeMemoryNotes(answers) {
  const wrongAnswers = getRecent(answers.filter(answer => !answer.correct), 800).reverse();
  const notes = [];
  const seen = new Set();

  for (const answer of wrongAnswers) {
    if (notes.length >= 8) break;
    if (seen.has(answer.qid)) continue;
    const question = questionByQid.get(answer.qid);
    if (!question) continue;
    if (!MEMORY_PATTERN.test(question.question)) continue;
    seen.add(answer.qid);
    notes.push({
      qid: answer.qid,
      label: `${question.source} Q${question.number} · ${question.subject}`,
      text: question.question,
    });
  }

  return notes;
}

function computeTrapPatternStats(answers) {
  const wrongAnswers = getRecent(answers.filter(answer => !answer.correct), 500);
  const counts = new Map();
  let taggedAnswers = 0;

  wrongAnswers.forEach(answer => {
    const words =
      Array.isArray(answer.trapWords) && answer.trapWords.length > 0
        ? answer.trapWords
        : detectTrapWords(answer.selectedOptionText || '');
    if (words.length > 0) taggedAnswers += 1;
    words.forEach(word => {
      counts.set(word, (counts.get(word) || 0) + 1);
    });
  });

  const top = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([word, count]) => ({ word, count }));

  return {
    totalWrong: wrongAnswers.length,
    taggedAnswers,
    top,
  };
}

function setTextById(id, text) {
  const element = document.getElementById(id);
  if (element) element.textContent = text;
}

function renderSubjectAccuracyBars(subjectStats) {
  const container = document.getElementById('subject-accuracy-bars');
  if (!container) return;

  if (subjectStats.every(stat => stat.total === 0)) {
    container.innerHTML = '<div class="dashboard-empty">아직 학습 데이터가 없습니다.</div>';
    return;
  }

  container.innerHTML = subjectStats
    .map(stat => {
      const width = stat.total > 0 ? stat.rate : 0;
      let fillClass = 'bar-fill';
      if (stat.total > 0 && stat.rate < 40) fillClass = 'bar-fill danger';
      else if (stat.total > 0 && stat.rate < 60) fillClass = 'bar-fill warn';

      return `
        <div class="bar-row">
          <div class="bar-label">${stat.subject}</div>
          <div class="bar-track"><div class="${fillClass}" style="width:${width}%;"></div></div>
          <div class="bar-value">${stat.total > 0 ? `${stat.rate}% (${stat.total})` : '데이터 없음'}</div>
        </div>
      `;
    })
    .join('');
}

function renderWeeklyTrend(answers) {
  const container = document.getElementById('weekly-trend');
  if (!container) return;

  const trend = computeWeeklyTrend(answers);
  const maxCount = Math.max(...trend.map(day => day.total), 1);

  container.innerHTML = trend
    .map(day => {
      const width = Math.round((day.total / maxCount) * 100);
      const valueText = day.total > 0 ? `${day.total}문항 · ${day.rate}%` : '0문항';
      return `
        <div class="trend-row">
          <div class="trend-label">${day.label}</div>
          <div class="trend-track"><div class="trend-fill" style="width:${width}%;"></div></div>
          <div class="trend-value">${valueText}</div>
        </div>
      `;
    })
    .join('');
}

function renderDailyRoutine(answers) {
  const container = document.getElementById('daily-routine');
  if (!container) return;

  const routine = computeDailyRoutine(answers);
  container.innerHTML = routine
    .map(item => {
      const rate = Math.min(100, safeRate(item.current, item.target));
      return `
        <div class="bar-row">
          <div class="bar-label">${item.title}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${rate}%;"></div></div>
          <div class="bar-value">${item.current}/${item.target}${item.unit}</div>
        </div>
      `;
    })
    .join('');
}

function renderTodayLearningTab() {
  const summaryElement = document.getElementById('today-learning-summary');
  const routineContainer = document.getElementById('today-routine-list');
  if (!summaryElement || !routineContainer) return;

  const state = loadProgressState();
  const answers = state.answers || [];
  const todayKey = getLocalDateKey(Date.now());
  const todayAnswers = answers.filter(answer => getLocalDateKey(answer.ts) === todayKey);
  const todayAccuracy = computeAccuracy(todayAnswers);
  const routine = computeDailyRoutine(answers);

  if (todayAnswers.length === 0) {
    summaryElement.textContent = '오늘 학습 시작 전입니다. 루틴 버튼을 눌러 바로 시작하세요.';
  } else {
    summaryElement.textContent = `오늘 ${todayAnswers.length}문항 풀이 · 정답률 ${todayAccuracy.rate}%`;
  }

  const actionMap = {
    solve: {
      emoji: '🎯',
      desc: '기출 20~30문항을 풀어 데이터와 감각을 쌓기',
      buttonLabel: '기출 25문항 시작',
      action: () => runRecommendedQuiz('전체 과목', 'normal', 25),
    },
    classify: {
      emoji: '🧩',
      desc: '틀린 문제를 오답 유형으로 분류해 재노출 차단',
      buttonLabel: '오답 집중 20문항',
      action: () => runRecommendedQuiz('전체 과목', 'wrong-note', 20),
    },
    recover: {
      emoji: '🔁',
      desc: '전날 틀린 문제를 다시 풀어 회복률 올리기',
      buttonLabel: '재도전 10문항',
      action: () => runRecommendedQuiz('전체 과목', 'wrong-note', 10),
    },
  };

  routineContainer.innerHTML = routine
    .map(item => {
      const config = actionMap[item.key];
      const progressRate = Math.min(100, safeRate(item.current, item.target));
      return `
        <div class="today-routine-card">
          <div class="today-routine-title">${config?.emoji || '✅'} ${item.title}</div>
          <div class="today-routine-desc">${config?.desc || ''}</div>
          <div class="today-routine-progress">${item.current}/${item.target}${item.unit}</div>
          <div class="bar-track" style="margin-bottom:10px;"><div class="bar-fill" style="width:${progressRate}%;"></div></div>
          <button class="btn-outline today-action-btn" data-today-action="${item.key}">${config?.buttonLabel || '시작'}</button>
        </div>
      `;
    })
    .join('');

  routineContainer.querySelectorAll('[data-today-action]').forEach(button => {
    button.addEventListener('click', () => {
      const key = button.getAttribute('data-today-action');
      const action = actionMap[key]?.action;
      if (action) action();
    });
  });

  const quickFrequent = document.getElementById('today-quick-frequent');
  const quickCycle = document.getElementById('today-quick-cycle');
  if (quickFrequent) {
    quickFrequent.onclick = () => runRecommendedQuiz('전체 과목', 'frequent-20', 20);
  }
  if (quickCycle) {
    quickCycle.onclick = () => runRecommendedQuiz('전체 과목', 'auto-cycle', 20);
  }
}

function renderErrorTypeBars(answers) {
  const container = document.getElementById('error-type-bars');
  if (!container) return;

  const stats = computeErrorTypeStats(answers);
  if (stats.totalWrong === 0) {
    container.innerHTML = '<div class="dashboard-empty">최근 오답 데이터가 없습니다.</div>';
    return;
  }

  const maxCount = Math.max(...Object.values(stats.counts), stats.unclassified, 1);
  const rows = [
    ...ERROR_TYPE_OPTIONS.map(option => ({
      key: option.key,
      label: option.label,
      count: stats.counts[option.key] || 0,
    })),
    { key: 'unclassified', label: '미분류', count: stats.unclassified },
  ];

  container.innerHTML = rows
    .map(row => {
      const width = Math.round((row.count / maxCount) * 100);
      const fillClass = row.key === 'unclassified' ? 'bar-fill warn' : 'bar-fill';
      return `
        <div class="bar-row">
          <div class="bar-label">${row.label}</div>
          <div class="bar-track"><div class="${fillClass}" style="width:${width}%;"></div></div>
          <div class="bar-value">${row.count}건</div>
        </div>
      `;
    })
    .join('');
}

function renderMemoryNotes(answers) {
  const container = document.getElementById('memory-notes-list');
  if (!container) return;

  const notes = computeMemoryNotes(answers);
  if (notes.length === 0) {
    container.innerHTML = '<div class="dashboard-empty">숫자/절차형 오답이 아직 없습니다.</div>';
    return;
  }

  container.innerHTML = notes
    .map(
      note => `
      <div class="note-item">
        <div class="note-label">${note.label}</div>
        <div class="note-text">${note.text}</div>
      </div>
    `
    )
    .join('');
}

function renderTrapPattern(answers) {
  const container = document.getElementById('trap-pattern-list');
  if (!container) return;

  const stats = computeTrapPatternStats(answers);
  if (stats.totalWrong === 0) {
    container.innerHTML = '<div class="dashboard-empty">오답 데이터가 없습니다.</div>';
    return;
  }
  if (stats.top.length === 0) {
    container.innerHTML = '<div class="dashboard-empty">함정 단어 패턴이 아직 집계되지 않았습니다.</div>';
    return;
  }

  container.innerHTML = `
    <div class="dashboard-empty">함정 단어 감지: ${stats.taggedAnswers}/${stats.totalWrong}개 오답</div>
    ${stats.top
      .map(
        item => `
      <div class="bar-row">
        <div class="bar-label">${item.word}</div>
        <div class="bar-track"><div class="bar-fill danger" style="width:${Math.min(
          100,
          item.count * 12
        )}%;"></div></div>
        <div class="bar-value">${item.count}회</div>
      </div>
    `
      )
      .join('')}
  `;
}

function runRecommendedQuiz(subject, mode, count) {
  const modeSelect = document.getElementById('quiz-mode');
  const subjectSelect = document.getElementById('quiz-subject');
  const countSelect = document.getElementById('quiz-count');
  if (!modeSelect || !subjectSelect || !countSelect) return;

  modeSelect.value = mode;
  modeSelect.dispatchEvent(new Event('change'));
  subjectSelect.value = subject;
  countSelect.value = String(count);

  document.querySelector('.nav-btn[data-target="quiz"]').click();
  startQuiz();
}

function renderRecommendation({ riskSubjects, recentCount, unresolvedWrongCount, weakSubject }) {
  const textElement = document.getElementById('home-recommend-text');
  const button = document.getElementById('home-recommend-btn');
  if (!textElement || !button) return;

  let subject = '전체 과목';
  let mode = 'frequent-20';
  let count = 20;
  let message = '빈출 20문제 세트로 실전 감각을 유지하세요.';
  let buttonText = '빈출 20세트 시작';

  if (unresolvedWrongCount >= 15) {
    subject = weakSubject || '전체 과목';
    mode = 'wrong-note';
    count = 20;
    message = `미해결 오답이 ${unresolvedWrongCount}개 있습니다. 오답 집중 복습으로 먼저 제거하세요.`;
    buttonText = '오답 집중 20문제';
  } else if (riskSubjects.length > 0) {
    subject = riskSubjects[0].subject;
    mode = 'frequent-priority';
    count = 20;
    message = `${subject} 과락 위험이 있어요. 빈출 우선 모드로 약점을 보완하세요.`;
    buttonText = `${subject} 집중 20문제`;
  } else if (recentCount < 20) {
    subject = '전체 과목';
    mode = 'normal';
    count = 10;
    message = '학습 초기입니다. 전체 과목 랜덤 10문제로 데이터부터 쌓으세요.';
    buttonText = '랜덤 10문제 시작';
  }

  textElement.textContent = message;
  button.textContent = buttonText;
  button.onclick = event => {
    event.stopPropagation();
    runRecommendedQuiz(subject, mode, count);
  };
}

function renderHomeDashboard() {
  const state = loadProgressState();
  const answers = state.answers;
  const quizzes = state.quizzes;

  const totalAccuracy = computeAccuracy(answers);
  const recent100 = computeAccuracy(getRecent(answers, 100));
  const subjectStats = computeSubjectStats(answers, 50);
  const learningStates = computeQuestionLearningState(answers);
  const unresolvedWrongCount = [...learningStates.values()].filter(item => item.needsReview).length;
  const riskSubjects = subjectStats
    .filter(stat => stat.total >= 5 && stat.rate < 45)
    .sort((a, b) => a.rate - b.rate);
  const readiness = computeReadiness(answers, quizzes, subjectStats);
  const frequentProgress = computeFrequentProgress(answers);
  const recoveryRate = computeRecoveryRate(answers);
  const pace = computePace(answers);

  setTextById('metric-pass-status', readiness.label);
  setTextById('metric-pass-sub', `${readiness.detail} · 미해결 오답 ${unresolvedWrongCount}개`);

  if (riskSubjects.length === 0) {
    setTextById('metric-risk-subject', '안정');
    setTextById('metric-risk-sub', '최근 50문항 기준 과락 위험 과목이 없습니다.');
  } else {
    setTextById('metric-risk-subject', riskSubjects.map(subject => subject.subject).join(', '));
    setTextById('metric-risk-sub', `최저: ${riskSubjects[0].subject} ${riskSubjects[0].rate}%`);
  }

  setTextById('metric-recent-accuracy', recent100.total > 0 ? `${recent100.rate}%` : '-');
  setTextById(
    'metric-recent-sub',
    recent100.total > 0
      ? `최근 ${recent100.total}문항 · 누적 ${totalAccuracy.rate}%`
      : '학습 데이터가 없습니다.'
  );

  setTextById('metric-frequent-progress', `${frequentProgress.progressRate}%`);
  setTextById(
    'metric-frequent-sub',
    `${frequentProgress.solvedUnique}/${frequentProgress.totalFrequentQuestions}문항 · 정답률 ${frequentProgress.accuracy.rate}%`
  );

  setTextById('metric-recovery-rate', recoveryRate.rate === null ? '-' : `${recoveryRate.rate}%`);
  setTextById(
    'metric-recovery-sub',
    recoveryRate.wrongQuestionCount > 0
      ? `${recoveryRate.recoveredQuestionCount}/${recoveryRate.wrongQuestionCount}개 오답 회복`
      : '오답 데이터가 없습니다.'
  );

  setTextById('metric-pace', pace.avgSec === null ? '-' : `${pace.avgSec}초`);
  setTextById(
    'metric-pace-sub',
    pace.avgSec === null
      ? '풀이 시간 데이터가 없습니다.'
      : `최근 ${pace.count}문항 · ${pace.status} (목표 ${TARGET_SECONDS_PER_QUESTION}초)`
  );

  renderSubjectAccuracyBars(subjectStats);
  renderWeeklyTrend(answers);
  renderDailyRoutine(answers);
  renderErrorTypeBars(answers);
  renderMemoryNotes(answers);
  renderTrapPattern(answers);

  const weakSubject = subjectStats
    .filter(stat => stat.total > 0)
    .sort((a, b) => a.rate - b.rate)[0]?.subject;

  renderRecommendation({
    riskSubjects,
    recentCount: recent100.total,
    unresolvedWrongCount,
    weakSubject,
  });
}

function setupQuizModeControls() {
  const modeSelect = document.getElementById('quiz-mode');
  const countSelect = document.getElementById('quiz-count');
  const modeHint = document.getElementById('quiz-mode-hint');
  if (!modeSelect || !countSelect || !modeHint) return;

  const applyMode = () => {
    const mode = modeSelect.value;
    if (mode === 'frequent-20') {
      countSelect.value = '20';
      countSelect.disabled = true;
      modeHint.textContent = '빈출 100선 기반으로 우선순위가 높은 20문항을 자동 구성합니다.';
      return;
    }

    countSelect.disabled = false;
    if (mode === 'wrong-note') {
      modeHint.textContent = '틀린 문제를 우선 재출제합니다. 오답 회복률을 올리는 데 가장 효과적입니다.';
      return;
    }
    if (mode === 'auto-cycle') {
      modeHint.textContent = '회독 단계(1~4)에 따라 문제를 자동 선택합니다.';
      return;
    }
    if (mode === 'frequent-priority') {
      modeHint.textContent = '선택한 과목에서 빈출 키워드가 매칭된 문항을 우선 출제합니다.';
      return;
    }

    modeHint.textContent = '일반 랜덤 모드: 기존 문제은행에서 무작위로 출제합니다.';
  };

  modeSelect.addEventListener('change', applyMode);
  applyMode();
}

// --- UI Navigation Logic ---
function initTabs() {
  const navBtns = document.querySelectorAll('.nav-btn');
  const tabs = document.querySelectorAll('.tab');

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');

      navBtns.forEach(button => button.classList.remove('active'));
      btn.classList.add('active');

      tabs.forEach(tab => tab.classList.remove('active'));
      document.getElementById(targetId).classList.add('active');

      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });

  const goToQuizCard = document.getElementById('go-to-quiz');
  if (goToQuizCard) {
    goToQuizCard.addEventListener('click', () => {
      document.querySelector('.nav-btn[data-target="quiz"]').click();
    });
  }
}

function setupMobileHomeCollapsibles() {
  const cards = document.querySelectorAll('.mobile-collapsible-card');
  if (cards.length === 0) return;

  cards.forEach(card => {
    const toggle = card.querySelector('.card-collapse-toggle');
    if (!toggle) return;

    if (!toggle.dataset.bound) {
      toggle.dataset.bound = '1';
      toggle.addEventListener('click', () => {
        const isCollapsed = card.classList.toggle('is-collapsed');
        toggle.setAttribute('aria-expanded', String(!isCollapsed));
      });
    }

    if (!card.dataset.mobileInitDone) {
      const defaultOpen = card.dataset.collapseDefault === 'open';
      card.classList.toggle('is-collapsed', !defaultOpen);
      toggle.setAttribute('aria-expanded', String(defaultOpen));
      card.dataset.mobileInitDone = '1';
      return;
    }

    const isCollapsed = card.classList.contains('is-collapsed');
    toggle.setAttribute('aria-expanded', String(!isCollapsed));
  });
}

// --- Subject List Logic ---
function buildSubjects() {
  const container = document.getElementById('subject-list');
  if (!container) return;

  subjectsData.forEach((subjectData, index) => {
    const summary = coreSummaryBySubject[subjectData.name]?.keyPoints || [];

    const card = document.createElement('div');
    card.className = 'subject-card';
    card.innerHTML = `
      <div class="subject-header" id="subj-header-${index}">
        <div>
          <div class="subject-title">${subjectData.name}</div>
          <div class="subject-meta">핵심 개념 ${subjectData.topics.length}개 · ${subjectData.count}</div>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <span class="badge ${subjectData.color}">${subjectData.count}</span>
          <span class="chevron" id="chev-${index}">▶</span>
        </div>
      </div>
      <div class="subject-body" id="body-${index}">
        ${subjectData.topics
          .map(topic => `
          <div class="topic-item">
            <div class="topic-name">${topic.name}</div>
            <div class="topic-desc">${topic.desc}</div>
            <div class="keyword-list">${topic.keywords.map(keyword => `<span class="keyword">${keyword}</span>`).join('')}</div>
          </div>
        `)
          .join('')}
        <div class="topic-item core-summary-item">
          <div class="topic-name">핵심요점정리 기반 요약</div>
          <div class="keyword-list">
            ${summary.slice(0, 8).map(point => `<span class="keyword core-keyword">${point}</span>`).join('')}
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);

    document.getElementById(`subj-header-${index}`).addEventListener('click', () => {
      const body = document.getElementById(`body-${index}`);
      const chevron = document.getElementById(`chev-${index}`);
      body.classList.toggle('open');
      chevron.classList.toggle('open');
    });
  });
}

// --- Quiz Logic ---
function shuffleArray(array) {
  const arr = [...array];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

function startQuiz() {
  const subject = document.getElementById('quiz-subject').value;
  const mode = document.getElementById('quiz-mode').value;
  const requestedCount = parseInt(document.getElementById('quiz-count').value, 10);
  const effectiveCount = mode === 'frequent-20' ? 20 : requestedCount;

  currentQuizMode = mode;
  currentQuizContext = { subject, requestedCount: effectiveCount };
  currentQuizStartedAt = Date.now();
  currentQuestionStartedAt = null;
  currentQuizAnswerLog = [];
  currentQuizContext.cycleStage = null;

  const subjectPool = filterQuestionsBySubject(enrichedQuestionsBank, subject);
  if (subjectPool.length === 0) {
    document.getElementById('quiz-content').innerHTML = `
      <div class="card" style="text-align: center; padding: 2rem;">
        <div style="font-size: 15px; color: var(--color-text-secondary);">해당 과목의 문제가 아직 등록되지 않았습니다.</div>
      </div>`;
    return;
  }

  let selectedQuestions = [];
  const progressState = loadProgressState();
  const learningStates = computeQuestionLearningState(progressState.answers || []);
  if (mode === 'frequent-priority') {
    const frequentOnly = subjectPool.filter(item => item.frequentScore > 0);
    const basePool = frequentOnly.length > 0 ? frequentOnly : subjectPool;
    selectedQuestions = sortByFrequentPriority(basePool).slice(0, effectiveCount);
  } else if (mode === 'frequent-20') {
    selectedQuestions = buildFrequentTwentySet(subjectPool, subject);
  } else if (mode === 'wrong-note') {
    const wrongSet = buildWrongNoteSet(subjectPool, effectiveCount, learningStates);
    selectedQuestions =
      wrongSet.length > 0 ? wrongSet : sortByFrequentPriority(subjectPool).slice(0, effectiveCount);
  } else if (mode === 'auto-cycle') {
    const cycleResult = buildAutoCycleSet(subjectPool, effectiveCount, progressState, subject);
    currentQuizContext.cycleStage = cycleResult.stage;
    selectedQuestions = cycleResult.items;
  } else {
    selectedQuestions = shuffleArray(subjectPool).slice(0, effectiveCount);
  }

  currentQuizList = uniqueByQid(selectedQuestions).map(question => {
    const originalAnswerText = question.options[question.answer];
    const shuffledOptions = shuffleArray(question.options);
    const newAnswerIndex = shuffledOptions.indexOf(originalAnswerText);
    return {
      ...question,
      options: shuffledOptions,
      answer: newAnswerIndex,
    };
  });

  currentQIndex = 0;
  score = 0;
  showQuestion();
}

function showQuestion() {
  if (currentQIndex >= currentQuizList.length) {
    showResult();
    return;
  }

  const question = currentQuizList[currentQIndex];
  const progress = Math.round((currentQIndex / currentQuizList.length) * 100);
  const quizContainer = document.getElementById('quiz-content');
  const modeLabel = currentQuizMode === 'auto-cycle' && currentQuizContext.cycleStage
    ? `${getQuizModeLabel(currentQuizMode)} (${currentQuizContext.cycleStage})`
    : getQuizModeLabel(currentQuizMode);

  const frequentBadge =
    question.frequentScore > 0 ? '<span class="badge badge-frequent">빈출</span>' : '';
  const frequentTagHtml = question.frequentTags?.length
    ? `<div class="frequent-tag-list">${question.frequentTags.map(tag => `<span class="frequent-tag">${tag}</span>`).join('')}</div>`
    : '';

  quizContainer.innerHTML = `
    <div class="quiz-box">
      <div class="quiz-q-num">문제 ${currentQIndex + 1} / ${currentQuizList.length} · 현재 점수: ${score}점 · 모드: ${modeLabel}</div>
      <div style="height:4px; background:var(--color-background-secondary); border-radius:2px; margin-bottom:1rem;">
        <div style="height:4px; width:${progress}%; background:var(--color-text-primary); border-radius:2px; transition:width 0.3s;"></div>
      </div>
      ${frequentBadge ? `<div class="quiz-meta-row">${frequentBadge}</div>` : ''}
      <div class="quiz-q">${question.question}</div>
      ${frequentTagHtml}
      ${question.options
        .map(
          (option, index) =>
            `<button class="option-btn" id="opt-${index}" data-index="${index}">${option}</button>`
        )
        .join('')}
      <div id="mistake-classifier" class="mistake-classifier" style="display:none;">
        <div class="mistake-title">오답 유형을 선택하세요 (오답노트 자동화)</div>
        <div class="mistake-buttons">
          ${ERROR_TYPE_OPTIONS.map(option => `<button class="mistake-btn" data-error-type="${option.key}">${option.label}</button>`).join('')}
        </div>
        <div class="mistake-selected" id="mistake-selected-label"></div>
      </div>
      <div id="explanation" style="display:none;" class="explanation"></div>
      <div class="quiz-nav">
        <span style="font-size: 13px; color: var(--color-text-secondary);" id="quiz-status">선택지를 클릭하세요</span>
        <button class="btn-outline" id="next-btn" style="display:none;">다음 문제 →</button>
      </div>
    </div>
  `;

  currentQuestionStartedAt = Date.now();

  document.querySelectorAll('.option-btn').forEach(button => {
    button.addEventListener('click', event => {
      const selectedIndex = parseInt(event.target.getAttribute('data-index'), 10);
      selectAnswer(selectedIndex);
    });
  });

  document.getElementById('next-btn').addEventListener('click', () => {
    currentQIndex += 1;
    showQuestion();
  });
}

function selectAnswer(selectedIndex) {
  const question = currentQuizList[currentQIndex];
  const isCorrect = selectedIndex === question.answer;
  const selectedOptionText = question.options[selectedIndex] || '';
  const correctOptionText = question.options[question.answer] || '';
  const trapWords = detectTrapWords(selectedOptionText);

  document.querySelectorAll('.option-btn').forEach(button => {
    button.disabled = true;
  });
  document.getElementById(`opt-${question.answer}`).classList.add('correct');

  const statusSpan = document.getElementById('quiz-status');
  if (isCorrect) {
    score += 1;
    statusSpan.textContent = '✓ 정답입니다!';
    statusSpan.style.color = '#9dd57b';
  } else {
    document.getElementById(`opt-${selectedIndex}`).classList.add('wrong');
    statusSpan.textContent = '✗ 오답입니다.';
    statusSpan.style.color = '#f39a9a';
  }

  const elapsedSec = currentQuestionStartedAt
    ? Math.max(1, Math.round((Date.now() - currentQuestionStartedAt) / 1000))
    : null;
  const answerRecord = {
    id: createRecordId('ans'),
    ts: Date.now(),
    qid: question.qid,
    source: question.source,
    number: question.number,
    subject: question.subject,
    correct: isCorrect,
    mode: currentQuizMode,
    frequentScore: Number(question.frequentScore || 0),
    elapsedSec,
    selectedOptionText,
    correctOptionText,
    trapWords,
    hasTrapWord: trapWords.length > 0,
    errorType: null,
  };
  currentQuizAnswerLog.push({ ...answerRecord });
  const savedAnswerId = appendAnswerRecord(answerRecord);

  const summary = coreSummaryBySubject[question.subject]?.keyPoints || [];
  const summaryText = summary.slice(0, 3).join(' · ');
  const frequentText = question.frequentTags?.length ? question.frequentTags.join(', ') : '';

  const explanation = document.getElementById('explanation');
  explanation.style.display = 'block';
  explanation.innerHTML = `
    <strong>해설:</strong> ${question.explanation || '정답 보기를 확인하세요.'}
    ${summaryText ? `<br><br><strong>핵심요약:</strong> ${summaryText}` : ''}
    ${frequentText ? `<br><strong>빈출연계:</strong> ${frequentText}` : ''}
  `;

  if (!isCorrect) {
    const classifier = document.getElementById('mistake-classifier');
    const selectedLabel = document.getElementById('mistake-selected-label');
    if (classifier && selectedLabel) {
      classifier.style.display = 'block';
      selectedLabel.textContent = '미분류';
      classifier.querySelectorAll('.mistake-btn').forEach(button => {
        button.addEventListener('click', () => {
          const type = button.getAttribute('data-error-type');
          updateAnswerRecord(savedAnswerId, { errorType: type });
          updateCurrentQuizAnswerLog(savedAnswerId, { errorType: type });
          selectedLabel.textContent = `선택됨: ${getErrorTypeLabel(type)}`;
          classifier.querySelectorAll('.mistake-btn').forEach(node => node.classList.remove('active'));
          button.classList.add('active');
          renderHomeDashboard();
          renderTodayLearningTab();
        });
      });
    }
  }

  document.getElementById('next-btn').style.display = 'block';
}

function showResult() {
  const total = currentQuizList.length;
  const percent = Math.round((score / total) * 100);
  const pass = percent >= 60;
  const frequentCount = currentQuizList.filter(item => item.frequentScore > 0).length;
  const durationSec = currentQuizStartedAt
    ? Math.max(1, Math.round((Date.now() - currentQuizStartedAt) / 1000))
    : null;

  const perSubject = SUBJECT_ORDER.map(subject => {
    const subjectAnswers = currentQuizAnswerLog.filter(answer => answer.subject === subject);
    const accuracy = computeAccuracy(subjectAnswers);
    return {
      subject,
      total: accuracy.total,
      rate: accuracy.rate,
    };
  }).filter(item => item.total > 0);

  appendQuizRecord({
    ts: Date.now(),
    mode: currentQuizMode,
    subject: currentQuizContext.subject,
    requestedCount: currentQuizContext.requestedCount,
    total,
    score,
    percent,
    durationSec,
    frequentCount,
    perSubject,
  });

  renderHomeDashboard();
  renderTodayLearningTab();

  document.getElementById('quiz-content').innerHTML = `
    <div class="quiz-box">
      <div style="text-align:center; padding: 1rem 0;">
        <div style="font-size: 14px; color: var(--color-text-secondary); margin-bottom: 8px;">퀴즈 완료! (${currentQuizMode === 'auto-cycle' && currentQuizContext.cycleStage ? `${getQuizModeLabel(currentQuizMode)} ${currentQuizContext.cycleStage}` : getQuizModeLabel(currentQuizMode)})</div>
        <div style="font-size: 36px; font-weight: 500;" class="${pass ? 'score-pass' : 'score-fail'}">${percent}점</div>
        <div style="font-size: 14px; color: var(--color-text-secondary); margin-top: 4px;">${score} / ${total} 문항 정답 · 빈출 문항 ${frequentCount}개 포함</div>
        <div style="margin-top: 12px; padding: 8px 16px; display:inline-block; border-radius: var(--border-radius-md); background: ${pass ? '#1c3520' : '#3a1f21'}; color: ${pass ? '#b9e69f' : '#f3b2b2'}; font-size: 14px; font-weight: 500;">
          ${pass ? '합격권 수준' : '추가 학습 필요'}
        </div>
        <div style="margin-top: 1.5rem; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
          <button class="btn-primary" id="retry-btn">다시 풀기</button>
          <button class="btn-outline" id="view-study-btn">학습 자료 보기</button>
        </div>
      </div>
    </div>
  `;

  document.getElementById('retry-btn').addEventListener('click', startQuiz);
  document.getElementById('view-study-btn').addEventListener('click', () => {
    document.querySelector('.nav-btn[data-target="study"]').click();
  });
}

// --- Auth Logic ---
function initAuth() {
  const logout = () => {
    localStorage.removeItem('currentUser');
    showAuth();
  };

  const currentUser = localStorage.getItem('currentUser');
  if (currentUser) {
    showMainApp(currentUser);
  } else {
    showAuth();
  }

  document.getElementById('auth-toggle-btn').addEventListener('click', () => {
    isLoginMode = !isLoginMode;
    document.getElementById('auth-title').textContent = isLoginMode ? '로그인' : '회원가입';
    document.getElementById('auth-desc').textContent = isLoginMode
      ? '유통관리사 2급 학습 플랫폼에 접속하세요.'
      : '새로운 계정을 생성하세요.';
    document.getElementById('auth-action-btn').textContent = isLoginMode ? '로그인' : '가입하기';
    document.getElementById('auth-toggle-text').textContent = isLoginMode
      ? '계정이 없으신가요?'
      : '이미 계정이 있으신가요?';
    document.getElementById('auth-toggle-btn').textContent = isLoginMode ? '회원가입' : '로그인';
    document.getElementById('auth-id').value = '';
    document.getElementById('auth-pw').value = '';
  });

  document.getElementById('auth-action-btn').addEventListener('click', handleAuth);
  document.getElementById('logout-btn')?.addEventListener('click', logout);
  document.getElementById('mobile-logout-btn')?.addEventListener('click', logout);
}

function handleAuth() {
  const idStr = document.getElementById('auth-id').value.trim();
  const pwStr = document.getElementById('auth-pw').value.trim();

  if (!idStr || !pwStr) {
    alert('아이디와 비밀번호를 모두 입력해주세요.');
    return;
  }

  const users = JSON.parse(localStorage.getItem('users_db') || '{}');

  if (isLoginMode) {
    if (users[idStr] && users[idStr] === pwStr) {
      localStorage.setItem('currentUser', idStr);
      showMainApp(idStr);
    } else {
      alert('아이디 또는 비밀번호가 일치하지 않습니다.');
    }
  } else if (users[idStr]) {
    alert('이미 존재하는 아이디입니다.');
  } else {
    users[idStr] = pwStr;
    localStorage.setItem('users_db', JSON.stringify(users));
    alert('회원가입이 완료되었습니다. 로그인해주세요.');
    document.getElementById('auth-toggle-btn').click();
  }
}

function showAuth() {
  currentUserId = null;
  document.getElementById('auth-container').style.display = 'block';
  document.getElementById('main-app-container').style.display = 'none';
  document.getElementById('auth-id').value = '';
  document.getElementById('auth-pw').value = '';
}

function showMainApp(userId) {
  currentUserId = userId;
  document.getElementById('auth-container').style.display = 'none';
  document.getElementById('main-app-container').style.display = 'block';
  document.getElementById('user-greeting').textContent = `${userId}님 환영합니다!`;
  renderQuestionBankSummary();
  renderHomeDashboard();
  renderTodayLearningTab();
  document.querySelector('.nav-btn[data-target="today"]')?.click();
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  setupMobileHomeCollapsibles();
  buildSubjects();
  setupQuizModeControls();
  initAuth();

  const startBtn = document.getElementById('start-btn');
  if (startBtn) {
    startBtn.addEventListener('click', startQuiz);
  }
});
