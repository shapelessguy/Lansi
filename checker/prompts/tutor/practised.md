# An exercise offered was done

Told to the tutor, as if the learner said it, once the learner has done an exercise the tutor offered in the chat and its log has been written, so that the tutor goes on from how it went.

Variables:
- `$title`: the title of the exercise
- `$status`: how it ended: finished, or abandoned when the learner left it
- `$results`: how many answers were right, partial and wrong, with the scores it came to, as JSON
- `$grades`: each instance with its grade, as the log of an exercise is given it (logs/record.md)
- `$log`: the log written of it, or `none` if there is none

## Prompt

[The learner did the exercise "$title" you offered; it ended $status.]

Results: $results

What was answered:
$grades

Its log:
$log
