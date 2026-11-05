// Local FSRS-6 so reviews keep their learning steps while offline. It mirrors
// the server's py-fsrs exactly (same weights, retention and steps, fuzz off);
// the server stays the source of truth and recomputes every review on sync.
// Known difference: ts-fsrs never shrinks a review interval, so an offline
// long-interval due date can land a day later than the server's. Memory state
// (stability, difficulty) matches to ~1e-8.

import { DefaultScheduler, type Grade } from "ts-fsrs";
import type { FsrsState, SchedulerParams } from "./api";

type Sched = Awaited<ReturnType<typeof DefaultScheduler<"FSRS-6">>>;
type StepUnit = `${number}m`;

// ts-fsrs schedule status by state; relearning cards are "learning" with state 3.
const STATUS = ["new", "learning", "review", "learning"] as const;
const DAY = 86_400_000;

export async function makeScheduler(p: SchedulerParams): Promise<Sched> {
  return DefaultScheduler({
    version: "FSRS-6",
    weights: p.weights,
    desiredRetention: p.desired_retention,
    enableShortTerm: true,
    learningSteps: p.learning_steps_minutes.map((m) => `${m}m` as StepUnit),
    relearningSteps: p.relearning_steps_minutes.map((m) => `${m}m` as StepUnit),
    enableFuzz: false,
    maximumInterval: p.maximum_interval,
  });
}

/** Server card state -> ts-fsrs card. py-fsrs has no "new" state: an unreviewed card is learning step 0. */
export function toTs(s: Sched, f: FsrsState, cardId: number, now: Date) {
  if (!f.last_review || f.stability == null || f.difficulty == null) return s.newCard({ now });
  const dueAt = new Date(f.due);
  const lastReviewAt = new Date(f.last_review);
  return {
    stability: f.stability,
    difficulty: f.difficulty,
    state: f.state,
    scheduleStatus: STATUS[f.state],
    dueAt,
    lastReviewAt,
    cardId: String(cardId),
    reps: 1,
    lapses: f.lapses,
    scheduledDays: Math.max(0, Math.round((dueAt.getTime() - lastReviewAt.getTime()) / DAY)),
    learningStep: f.step ?? 0,
  } as ReturnType<Sched["newCard"]>;
}

/** Apply one rating locally and return the new state in the server's shape. */
export function review(s: Sched, f: FsrsState, cardId: number, grade: 1 | 2 | 3 | 4, now: Date): FsrsState {
  const card = s.review({ card: toTs(s, f, cardId, now), grade: grade as Grade, now }).card;
  const wasReview = f.state === 2;
  return {
    state: card.state,
    step: card.state === 2 ? null : card.learningStep,
    stability: card.stability,
    difficulty: card.difficulty,
    due: new Date(card.dueAt).toISOString(),
    last_review: new Date(card.lastReviewAt ?? now).toISOString(),
    lapses: f.lapses + (grade === 1 && wasReview ? 1 : 0),
  };
}
