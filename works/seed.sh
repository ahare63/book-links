#!/bin/sh
# Adds the seed corpus. Run from the repository root: sh works/seed.sh
# Each line fetches one file by ID (cached after the first run), two seconds apart.
# Years are original publication dates; negative years are BC. A translation also gives the
# year the translation was made, because its English wording dates from then.
set -e
BL="${BOOK_LINKS:-.venv/bin/book-links}"

add() {  # id, year, author, title, [--translation-year=YEAR]
  "$BL" add-book "$1" --year="$2" --author "$3" --title "$4" $5
}

add 2199  -750 "Homer" "The Iliad" --translation-year=1898
add 3160  -725 "Homer" "The Odyssey" --translation-year=1725
add 7142  -400 "Thucydides" "History of the Peloponnesian War" --translation-year=1874
add 1600  -385 "Plato" "Symposium" --translation-year=1871
add 150   -375 "Plato" "The Republic" --translation-year=1871
add 228   -19  "Virgil" "The Aeneid" --translation-year=1697
add 2680  180  "Marcus Aurelius" "Meditations" --translation-year=1634
add 66057 1010 "Murasaki Shikibu" "The Tale of Genji" --translation-year=1925
add 8800  1320 "Dante Alighieri" "The Divine Comedy" --translation-year=1814
add 52617 1353 "Giovanni Boccaccio" "The Decameron" --translation-year=1620
add 1232  1532 "Niccolò Machiavelli" "The Prince" --translation-year=1908
add 35330 1592 "Thomas Kyd" "The Spanish Tragedy"
add 1524  1603 "William Shakespeare" "Hamlet"  # modern spelling; 1122 is the First Folio text
add 1533  1606 "William Shakespeare" "Macbeth"
add 10    1611 "Various" "King James Bible"
add 100   1623 "William Shakespeare" "Complete Works of Shakespeare"
add 20    1667 "John Milton" "Paradise Lost"
add 2527  1774 "Johann Wolfgang von Goethe" "The Sorrows of Young Werther" --translation-year=1854
add 147   1776 "Thomas Paine" "Common Sense"
add 14460 1808 "Johann Wolfgang von Goethe" "Faust" --translation-year=1856
add 1342  1813 "Jane Austen" "Pride and Prejudice"
add 84    1818 "Mary Shelley" "Frankenstein"
add 23684 1820 "John Keats" "Poems Published in 1820"
add 1260  1847 "Charlotte Brontë" "Jane Eyre"
add 768   1847 "Emily Brontë" "Wuthering Heights"
add 61    1848 "Karl Marx and Friedrich Engels" "The Communist Manifesto" --translation-year=1888
add 15    1851 "Herman Melville" "Moby-Dick"
add 11231 1853 "Herman Melville" "Bartleby, the Scrivener"
add 135   1862 "Victor Hugo" "Les Misérables" --translation-year=1887
add 145   1871 "George Eliot" "Middlemarch"
add 174   1890 "Oscar Wilde" "The Picture of Dorian Gray"
add 209   1898 "Henry James" "The Turn of the Screw"
add 4584  1904 "Henry Adams" "Mont-Saint-Michel and Chartres"
add 140   1906 "Upton Sinclair" "The Jungle"
add 175   1910 "Gaston Leroux" "The Phantom of the Opera" --translation-year=1911
add 8129  1910 "Lord Dunsany" "A Dreamer's Tales"
add 1845  1911 "Max Beerbohm" "Zuleika Dobson"
add 7178  1913 "Marcel Proust" "Swann's Way" --translation-year=1922
add 2814  1914 "James Joyce" "Dubliners"
add 1280  1915 "Edgar Lee Masters" "Spoon River Anthology"
add 4217  1916 "James Joyce" "A Portrait of the Artist as a Young Man"
add 805   1920 "F. Scott Fitzgerald" "This Side of Paradise"
add 4300  1922 "James Joyce" "Ulysses"
add 1321  1922 "T. S. Eliot" "The Waste Land"
add 60962 1923 "F. Scott Fitzgerald" "The Vegetable"
add 64317 1925 "F. Scott Fitzgerald" "The Great Gatsby"
add 71865 1925 "Virginia Woolf" "Mrs Dalloway"
add 67138 1926 "Ernest Hemingway" "The Sun Also Rises"
add 67098 1926 "A. A. Milne" "Winnie-the-Pooh"
add 73011 1928 "A. A. Milne" "The House at Pooh Corner"
add 75011 1929 "Erich Maria Remarque" "All Quiet on the Western Front" --translation-year=1929
add 75170 1929 "William Faulkner" "The Sound and the Fury"
add 77600 1930 "Dashiell Hammett" "The Maltese Falcon"
add 78221 1930 "Sigmund Freud" "Civilization and Its Discontents" --translation-year=1930

# Out of copyright in Australia, not in the United States: analysed locally, never committed.
"$BL" add-url "https://gutenberg.net.au/ebooks03/0301261.txt" \
  --title "Tender Is the Night" --author "F. Scott Fitzgerald" --year 1934

"$BL" add-stub --title "Infinite Jest" --author "David Foster Wallace" --year 1996

"$BL" add-subworks works/subworks.yaml
