// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

//! The JSON document served to other applications.

use anki_proto::decks::DeckTreeNode;
use serde::Serialize;

#[derive(Serialize, Clone, Debug, Default)]
pub(crate) struct Status {
    /// Unix seconds of the last sync that succeeded since startup.
    pub last_sync: Option<i64>,
    /// Why the most recent sync failed, if it did. The decks are then those
    /// of the last sync that worked.
    pub last_sync_error: Option<String>,
    /// Unix seconds at which the due counts were calculated.
    pub counted_at: i64,
    pub decks: Vec<DeckStatus>,
}

/// The counts match the ones in Anki's deck list: they include subdecks, and
/// the due counts have the daily limits applied.
#[derive(Serialize, Clone, Debug, PartialEq, Eq)]
pub(crate) struct DeckStatus {
    pub id: i64,
    /// The full name, e.g. `Languages::Spanish`.
    pub name: String,
    pub new: u32,
    pub learning: u32,
    pub review: u32,
    pub total_cards: u32,
}

/// Lists every deck in `tree`, parents before their children.
pub(crate) fn decks_in_tree(tree: &DeckTreeNode) -> Vec<DeckStatus> {
    let mut decks = vec![];
    for child in &tree.children {
        add_deck(child, None, &mut decks);
    }
    decks
}

fn add_deck(node: &DeckTreeNode, parent_name: Option<&str>, decks: &mut Vec<DeckStatus>) {
    let name = match parent_name {
        Some(parent) => format!("{parent}::{}", node.name),
        None => node.name.clone(),
    };
    decks.push(DeckStatus {
        id: node.deck_id,
        name: name.clone(),
        new: node.new_count,
        learning: node.learn_count,
        review: node.review_count,
        total_cards: node.total_including_children,
    });
    for child in &node.children {
        add_deck(child, Some(&name), decks);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(deck_id: i64, name: &str, children: Vec<DeckTreeNode>) -> DeckTreeNode {
        DeckTreeNode {
            deck_id,
            name: name.into(),
            children,
            ..Default::default()
        }
    }

    #[test]
    fn decks_in_tree_gives_subdecks_their_full_name_after_the_parent() {
        let tree = node(
            0,
            "",
            vec![
                node(
                    1,
                    "Languages",
                    vec![node(2, "Spanish", vec![node(3, "Verbs", vec![])])],
                ),
                node(4, "Maths", vec![]),
            ],
        );

        let decks = decks_in_tree(&tree);

        let names: Vec<_> = decks
            .iter()
            .map(|deck| (deck.id, deck.name.as_str()))
            .collect();
        assert_eq!(
            names,
            [
                (1, "Languages"),
                (2, "Languages::Spanish"),
                (3, "Languages::Spanish::Verbs"),
                (4, "Maths"),
            ]
        );
    }

    #[test]
    fn decks_in_tree_reports_the_limited_due_counts_and_total_with_subdecks() {
        let deck = DeckTreeNode {
            deck_id: 1,
            name: "Maths".into(),
            new_count: 5,
            learn_count: 2,
            review_count: 30,
            new_uncapped: 400,
            review_uncapped: 90,
            total_in_deck: 10,
            total_including_children: 500,
            ..Default::default()
        };
        let tree = node(0, "", vec![deck]);

        let decks = decks_in_tree(&tree);

        assert_eq!(
            decks,
            [DeckStatus {
                id: 1,
                name: "Maths".into(),
                new: 5,
                learning: 2,
                review: 30,
                total_cards: 500,
            }]
        );
    }

    #[test]
    fn decks_in_tree_is_empty_when_there_are_no_decks() {
        assert_eq!(decks_in_tree(&node(0, "", vec![])), []);
    }
}
