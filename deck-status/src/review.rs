// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! Studies a deck as the reviewer of Anki does: the next card of its queue,
//! rendered, with what each of the four buttons would do, and the answer
//! given to it. These are the only requests here that change the
//! collection, and what they change is synced like a review made anywhere
//! else.
//!
//! The scheduler takes everything from the collection as it was synced: the
//! options of each deck, such as its limits, learning steps and FSRS, the
//! preferences, and when the day starts. Only what the reviewer shows is
//! read here, as `Settings`.

use std::time::SystemTime;
use std::time::UNIX_EPOCH;

use anki::backend::Backend;
use anki_proto::card_rendering::av_tag;
use anki_proto::card_rendering::rendered_template_node;
use anki_proto::card_rendering::ExtractAvTagsRequest;
use anki_proto::card_rendering::ExtractAvTagsResponse;
use anki_proto::card_rendering::RenderCardResponse;
use anki_proto::card_rendering::RenderExistingCardRequest;
use anki_proto::collection::OpChanges;
use anki_proto::config::Preferences;
use anki_proto::deck_config::DeckConfig;
use anki_proto::deck_config::DeckConfigId;
use anki_proto::decks::deck;
use anki_proto::decks::Deck;
use anki_proto::decks::DeckId;
use anki_proto::generic::Empty;
use anki_proto::generic::StringList;
use anki_proto::scheduler::card_answer::Rating;
use anki_proto::scheduler::queued_cards::Queue;
use anki_proto::scheduler::queued_cards::QueuedCard;
use anki_proto::scheduler::CardAnswer;
use anki_proto::scheduler::GetQueuedCardsRequest;
use anki_proto::scheduler::QueuedCards;
use anyhow::anyhow;
use anyhow::Context;
use anyhow::Result;
use prost::Message;
use serde::Serialize;

use crate::api;

/// The deck being studied, as the reviewer shows it.
#[derive(Serialize, Debug)]
pub(crate) struct Shown {
    /// None once nothing more is due today.
    pub card: Option<ShownCard>,
    /// What is left of the deck today, with its daily limits applied.
    pub counts: Counts,
}

#[derive(Serialize, Debug, PartialEq, Eq)]
pub(crate) struct Counts {
    pub new: u32,
    pub learning: u32,
    pub review: u32,
}

#[derive(Serialize, Debug)]
pub(crate) struct ShownCard {
    pub id: i64,
    pub note_id: i64,
    /// The number of its template, from 1, as the class `card1` of the
    /// reviewer has it.
    pub ord: u32,
    /// "new", "learning" or "review".
    pub queue: &'static str,
    /// The two sides as HTML, with each sound or text to be read aloud
    /// replaced by `[anki:play:q:N]` or `[anki:play:a:N]`, N the place of
    /// it in `question_av` or `answer_av`. Media are named as they are in
    /// the media folder.
    pub question: String,
    pub answer: String,
    pub css: String,
    pub question_av: Vec<Av>,
    pub answer_av: Vec<Av>,
    /// When the card would be due again after Again, Hard, Good and Easy,
    /// such as "<10m" or "3d".
    pub labels: Vec<String>,
    pub settings: Settings,
}

/// A sound or video of a card, or text it has read aloud.
#[derive(Serialize, Debug, PartialEq)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub(crate) enum Av {
    Sound {
        file: String,
    },
    Tts {
        text: String,
        lang: String,
        speed: f32,
    },
}

/// What the options of the card's deck and the preferences say of how the
/// reviewer shows it.
#[derive(Serialize, Debug, Default)]
pub(crate) struct Settings {
    pub autoplay: bool,
    pub skip_question_when_replaying_answer: bool,
    pub show_timer: bool,
    pub show_intervals_on_buttons: bool,
    pub show_remaining_due_counts: bool,
    pub hide_audio_play_buttons: bool,
}

/// What came of an answer, with the card to study next.
#[derive(Serialize, Debug)]
pub(crate) struct Answered {
    /// False if the card was not the one at the top of the queue, as when a
    /// sync brought a review of it from elsewhere; nothing was recorded.
    pub answered: bool,
    #[serde(flatten)]
    pub next: Shown,
}

/// The next card of `deck_id` and its subdecks.
pub(crate) fn next(backend: &Backend, deck_id: i64) -> Result<Shown> {
    study(backend, deck_id)?;
    let (top, counts) = top_of_queue(backend)?;
    let card = top.map(|queued| show(backend, &queued)).transpose()?;
    Ok(Shown { card, counts })
}

/// Answers the card `card_id` of `deck_id` with `rating`, 1 to 4 for Again
/// to Easy as the keys of the reviewer are, after `millis` of looking at
/// it, and returns the next card.
pub(crate) fn answer(
    backend: &Backend,
    deck_id: i64,
    card_id: i64,
    rating: u8,
    millis: u32,
) -> Result<Answered> {
    let rating = match rating {
        1 => Rating::Again,
        2 => Rating::Hard,
        3 => Rating::Good,
        4 => Rating::Easy,
        _ => return Err(anyhow!("a card is answered with 1 to 4")),
    };
    study(backend, deck_id)?;
    let (top, _) = top_of_queue(backend)?;
    let Some(queued) = top.filter(|queued| card_id_of(queued) == card_id) else {
        return Ok(Answered {
            answered: false,
            next: next(backend, deck_id)?,
        });
    };
    let states = queued.states.context("the card has no states")?;
    let new_state = match rating {
        Rating::Again => states.again,
        Rating::Hard => states.hard,
        Rating::Good => states.good,
        Rating::Easy => states.easy,
    };
    let answer = CardAnswer {
        card_id,
        current_state: states.current,
        new_state,
        rating: rating.into(),
        answered_at_millis: now_millis(),
        // the deck's options cap it as they do in Anki
        milliseconds_taken: millis,
    };
    let _: OpChanges = run(backend, "answerCard", &answer)?;
    Ok(Answered {
        answered: true,
        next: next(backend, deck_id)?,
    })
}

/// Has the queue be that of `deck_id`, which makes it the current deck of
/// the collection, as studying it in Anki does.
fn study(backend: &Backend, deck_id: i64) -> Result<()> {
    let current: Deck = run(backend, "getCurrentDeck", &Empty {})?;
    if current.id != deck_id {
        // fails for a deck there is not
        let _: Deck = run(backend, "getDeck", &DeckId { did: deck_id })?;
        let _: OpChanges = run(backend, "setCurrentDeck", &DeckId { did: deck_id })?;
    }
    Ok(())
}

fn top_of_queue(backend: &Backend) -> Result<(Option<QueuedCard>, Counts)> {
    let request = GetQueuedCardsRequest {
        fetch_limit: 1,
        intraday_learning_only: false,
    };
    let queued: QueuedCards = run(backend, "getQueuedCards", &request)?;
    let counts = Counts {
        new: queued.new_count,
        learning: queued.learning_count,
        review: queued.review_count,
    };
    Ok((queued.cards.into_iter().next(), counts))
}

fn card_id_of(queued: &QueuedCard) -> i64 {
    queued.card.as_ref().map_or(0, |card| card.id)
}

fn show(backend: &Backend, queued: &QueuedCard) -> Result<ShownCard> {
    let card = queued.card.as_ref().context("the queue gave no card")?;
    let rendered: RenderCardResponse = run(
        backend,
        "renderExistingCard",
        &RenderExistingCardRequest {
            card_id: card.id,
            browser: false,
            partial_render: false,
        },
    )?;
    let (question, question_av) = with_av_tags(backend, joined(&rendered.question_nodes), true)?;
    let (answer, answer_av) = with_av_tags(backend, joined(&rendered.answer_nodes), false)?;
    let states = queued.states.clone().context("the card has no states")?;
    let labels: StringList = run(backend, "describeNextStates", &states)?;
    let deck_id = if card.original_deck_id != 0 {
        card.original_deck_id
    } else {
        card.deck_id
    };
    Ok(ShownCard {
        id: card.id,
        note_id: card.note_id,
        ord: card.template_idx + 1,
        queue: match queued.queue() {
            Queue::New => "new",
            Queue::Learning => "learning",
            Queue::Review => "review",
        },
        question,
        answer,
        css: rendered.css,
        question_av,
        answer_av,
        labels: labels.vals,
        settings: settings(backend, deck_id)?,
    })
}

/// The text of rendered nodes. Rendered whole, they are all text.
fn joined(nodes: &[anki_proto::card_rendering::RenderedTemplateNode]) -> String {
    nodes
        .iter()
        .filter_map(|node| match &node.value {
            Some(rendered_template_node::Value::Text(text)) => Some(text.as_str()),
            Some(rendered_template_node::Value::Replacement(replacement)) => {
                Some(replacement.current_text.as_str())
            }
            None => None,
        })
        .collect()
}

fn with_av_tags(backend: &Backend, text: String, question_side: bool) -> Result<(String, Vec<Av>)> {
    let extracted: ExtractAvTagsResponse = run(
        backend,
        "extractAvTags",
        &ExtractAvTagsRequest {
            text,
            question_side,
        },
    )?;
    let tags = extracted
        .av_tags
        .into_iter()
        .filter_map(|tag| match tag.value? {
            av_tag::Value::SoundOrVideo(file) => Some(Av::Sound { file }),
            av_tag::Value::Tts(tts) => Some(Av::Tts {
                text: tts.field_text,
                lang: tts.lang,
                speed: tts.speed,
            }),
        })
        .collect();
    Ok((extracted.text, tags))
}

fn settings(backend: &Backend, deck_id: i64) -> Result<Settings> {
    let deck: Deck = run(backend, "getDeck", &DeckId { did: deck_id })?;
    let config_id = match deck.kind {
        Some(deck::Kind::Normal(normal)) => normal.config_id,
        // a card's own deck is never filtered; the default options else
        _ => 1,
    };
    let config: DeckConfig = run(backend, "getDeckConfig", &DeckConfigId { dcid: config_id })?;
    let options = config.config.unwrap_or_default();
    let preferences: Preferences = run(backend, "getPreferences", &Empty {})?;
    let reviewing = preferences.reviewing.unwrap_or_default();
    Ok(Settings {
        autoplay: !options.disable_autoplay,
        skip_question_when_replaying_answer: options.skip_question_when_replaying_answer,
        show_timer: options.show_timer,
        show_intervals_on_buttons: reviewing.show_intervals_on_buttons,
        show_remaining_due_counts: reviewing.show_remaining_due_counts,
        hide_audio_play_buttons: reviewing.hide_audio_play_buttons,
    })
}

fn run<I: Message, O: Message + Default>(backend: &Backend, method: &str, input: &I) -> Result<O> {
    api::run(backend, method, input)
        .map_err(|err| anyhow!(err))
        .with_context(|| format!("running {method}"))
}

fn now_millis() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_millis() as i64)
}

#[cfg(test)]
mod tests {
    use anki_proto::decks::DeckNames;
    use anki_proto::decks::GetDeckNamesRequest;
    use anki_proto::notes::AddNoteRequest;
    use anki_proto::notes::AddNoteResponse;
    use anki_proto::notes::Note;
    use anki_proto::notetypes::NotetypeId;
    use anki_proto::notetypes::NotetypeNames;
    use tempfile::TempDir;

    use super::*;
    use crate::mirror::open_backend;

    /// A new collection with a note of the type Basic for each of `fronts`,
    /// in the default deck.
    fn backend_with_notes(fronts: &[&str]) -> (Backend, TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let backend = open_backend(&dir.path().join("collection.anki2")).unwrap();
        let names: NotetypeNames = run(&backend, "getNotetypeNames", &Empty {}).unwrap();
        let basic = names
            .entries
            .iter()
            .find(|entry| entry.name == "Basic")
            .unwrap()
            .id;
        for front in fronts {
            let mut note: Note = run(&backend, "newNote", &NotetypeId { ntid: basic }).unwrap();
            note.fields = vec![front.to_string(), format!("back of {front}")];
            let request = AddNoteRequest {
                note: Some(note),
                deck_id: 1,
            };
            let _: AddNoteResponse = run(&backend, "addNote", &request).unwrap();
        }
        (backend, dir)
    }

    #[test]
    fn next_shows_the_first_new_card_with_a_label_for_each_button() {
        let (backend, _dir) = backend_with_notes(&["Hund [sound:hund.mp3]", "Katze"]);

        let shown = next(&backend, 1).unwrap();

        let card = shown.card.unwrap();
        assert_eq!(card.queue, "new");
        assert!(
            card.question.contains("Hund [anki:play:q:0]"),
            "{}",
            card.question
        );
        assert!(card.answer.contains("back of Hund"), "{}", card.answer);
        assert_eq!(
            card.question_av,
            vec![Av::Sound {
                file: "hund.mp3".into()
            }]
        );
        assert_eq!(card.labels.len(), 4);
        assert!(card.settings.autoplay);
        assert_eq!(
            shown.counts,
            Counts {
                new: 2,
                learning: 0,
                review: 0
            }
        );
    }

    #[test]
    fn answer_records_the_review_and_shows_the_next_card() {
        let (backend, _dir) = backend_with_notes(&["Hund", "Katze"]);
        let first = next(&backend, 1).unwrap().card.unwrap();

        let answered = answer(&backend, 1, first.id, 3, 4000).unwrap();

        assert!(answered.answered);
        let then = answered.next.card.unwrap();
        assert_ne!(then.id, first.id);
        assert_eq!(answered.next.counts.new, 1);
        let reviews: Vec<Vec<i64>> = serde_json::from_slice(
            &api::query(
                &backend,
                br#"{"sql": "select cid, ease, time from revlog"}"#,
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(reviews, vec![vec![first.id, 3, 4000]]);
    }

    #[test]
    fn answer_records_nothing_when_the_card_is_not_at_the_top_of_the_queue() {
        let (backend, _dir) = backend_with_notes(&["Hund", "Katze"]);
        let first = next(&backend, 1).unwrap().card.unwrap();

        let answered = answer(&backend, 1, first.id + 12345, 3, 1000).unwrap();

        assert!(!answered.answered);
        assert_eq!(answered.next.card.unwrap().id, first.id);
    }

    #[test]
    fn answer_refuses_a_rating_that_is_no_button() {
        let (backend, _dir) = backend_with_notes(&["Hund"]);
        let first = next(&backend, 1).unwrap().card.unwrap();

        assert!(answer(&backend, 1, first.id, 0, 1000).is_err());
        assert!(answer(&backend, 1, first.id, 5, 1000).is_err());
    }

    #[test]
    fn next_shows_no_card_once_nothing_is_due() {
        let (backend, _dir) = backend_with_notes(&["Hund"]);
        let first = next(&backend, 1).unwrap().card.unwrap();

        let answered = answer(&backend, 1, first.id, 4, 1000).unwrap();

        assert!(answered.next.card.is_none());
        assert_eq!(answered.next.counts.new, 0);
    }

    #[test]
    fn next_fails_for_a_deck_there_is_not() {
        let (backend, _dir) = backend_with_notes(&["Hund"]);
        let names: DeckNames = run(
            &backend,
            "getDeckNames",
            &GetDeckNamesRequest {
                skip_empty_default: false,
                include_filtered: true,
            },
        )
        .unwrap();
        let missing = names.entries.iter().map(|entry| entry.id).max().unwrap() + 1;

        assert!(next(&backend, missing).is_err());
    }
}
