# Shin Kanzen Master N1 Grammar Deck

This directory contains the data and assets for the "Shin Kanzen Master N1 Grammar" Anki deck.

## Data Structure

- `notes.csv`: The primary data file. It uses `#html:true` and contains 22 columns.
- `medias/`: Contains the `.mp3` audio files referenced in `notes.csv`.
- `templates/`: Contains the Anki card templates.
    - `front.html`: The front side of the card.
    - `back.html`: The back side of the card.
    - `style.css`: The styling for both sides.

## Import Instructions

1.  Open Anki.
2.  Click "Import File".
3.  Select `notes.csv`.
4.  Ensure the "Type" is set to the correct note type and the "Deck" is set correctly.
5.  Make sure "Allow HTML in fields" is checked.
6.  Copy the contents of `medias/` to your Anki `collection.media` folder.
7.  Copy and paste the contents of `templates/front.html`, `templates/back.html`, and `templates/style.css` into the corresponding sections of your Anki note type.
