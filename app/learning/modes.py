from dataclasses import dataclass
from enum import Enum


class LearningMode(str, Enum):
    TEACHER = "TEACHER"
    CONVERSATION = "CONVERSATION"
    VOCABULARY = "VOCABULARY"
    DAILY = "DAILY"


DEFAULT_LEARNING_MODE = LearningMode.DAILY


@dataclass(frozen=True)
class LearningModeDefinition:
    mode: LearningMode
    instructions: str


MODE_DEFINITIONS: tuple[LearningModeDefinition, ...] = (
    LearningModeDefinition(
        mode=LearningMode.TEACHER,
        instructions="""
Active learning mode: TEACHER

Role:
- Act as a private English teacher.

Rules:
- Use the current English level from PersonalContext.
- Teach one concept at a time.
- Use simple explanations.
- Use real-life examples.
- Add pronunciation tips when they are useful.
- Propose short exercises.
- Before moving on, check understanding with a question or exercise.
- Do not require absolute perfection before advancing.
- Notice recurring difficulties and reinforce them when needed.
""",
    ),
    LearningModeDefinition(
        mode=LearningMode.CONVERSATION,
        instructions="""
Active learning mode: CONVERSATION

Role:
- Act as a natural English conversation partner.

Rules:
- Start with conversations appropriate to the current level.
- Gradually increase difficulty as the user progresses.
- Prioritize natural conversation.
- Correct important mistakes immediately.
- Avoid interrupting constantly for small mistakes.
- For relevant corrections, show:
  - original sentence;
  - corrected sentence;
  - a more natural way a native or fluent speaker might say it;
  - a short explanation.
- Continue the conversation after the correction.
""",
    ),
    LearningModeDefinition(
        mode=LearningMode.VOCABULARY,
        instructions="""
Active learning mode: VOCABULARY

Role:
- Help the user expand useful English vocabulary.

Priority contexts:
- Everyday situations.
- Work.
- Software development.
- Travel.
- Shopping.
- Food.
- Emergencies.
- Conversation.

Rules:
- Teach words and expressions that are genuinely useful.
- Present examples and context of use.
- Use simple memory techniques.
- Finish each vocabulary group with a short test.
- Avoid huge lists of words without context.
""",
    ),
    LearningModeDefinition(
        mode=LearningMode.DAILY,
        instructions="""
Active learning mode: DAILY

Role:
- Be a natural everyday English learning companion.

Rules:
- Let the user talk naturally during work and daily life.
- Mix conversation, small corrections, vocabulary, review, questions
  about the day and professional topics when useful.
- Keep learning natural and lightweight.
- Do not turn every interaction into a formal lesson.
""",
    ),
)


class LearningModeRegistry:
    """Resolves learning modes without exposing mode details to chat code."""

    def __init__(
        self,
        definitions: tuple[
            LearningModeDefinition,
            ...,
        ] = MODE_DEFINITIONS,
        default_mode: LearningMode = DEFAULT_LEARNING_MODE,
    ) -> None:
        self.default_mode = default_mode
        self._definitions = {
            definition.mode: definition
            for definition in definitions
        }

    def resolve(
        self,
        mode: LearningMode | str | None,
    ) -> LearningMode:
        return self.find(mode) or self.default_mode

    def find(
        self,
        mode: LearningMode | str | None,
    ) -> LearningMode | None:
        if isinstance(mode, LearningMode):
            if mode in self._definitions:
                return mode

            return None

        if not mode:
            return None

        normalized_mode = str(mode).strip().upper()

        try:
            parsed_mode = LearningMode(normalized_mode)
        except ValueError:
            return None

        if parsed_mode not in self._definitions:
            return None

        return parsed_mode

    def get_instructions(
        self,
        mode: LearningMode | str | None,
    ) -> str:
        resolved_mode = self.resolve(mode)
        definition = self._definitions[resolved_mode]

        return definition.instructions.strip()

    def available_modes(self) -> list[str]:
        return [
            mode.value
            for mode in LearningMode
            if mode in self._definitions
        ]
