/** Starter list: restaurants roughly within 1 km of S+U Friedrichstraße, Berlin. Verify hours before relying on them. */
type Seed = { name: string; cuisine: string; address: string; website_url?: string };

export const FRIEDRICHSTRASSE_SEED: Seed[] = [
  { name: "Ständige Vertretung", cuisine: "German / Rhenish", address: "Schiffbauerdamm 8, 10117 Berlin" },
  { name: "Maximilians", cuisine: "German / Bavarian", address: "Friedrichstraße 185-190, 10117 Berlin" },
  { name: "Grill Royal", cuisine: "Steakhouse", address: "Friedrichstraße 105b, 10117 Berlin" },
  { name: "Borchardt", cuisine: "German / French", address: "Französische Straße 47, 10117 Berlin" },
  { name: "Augustiner am Gendarmenmarkt", cuisine: "German / Bavarian", address: "Charlottenstraße 55, 10117 Berlin" },
  { name: "Cadadia", cuisine: "Quiche & salads", address: "Charlottenstraße 63, 10117 Berlin" },
  { name: "Little Green Rabbit", cuisine: "Salads & soups", address: "Jägerstraße 27, 10117 Berlin" },
  { name: "Otito", cuisine: "Asian", address: "Leipziger Straße 30, 10117 Berlin" },
];

export const mapUrl = (name: string, address: string) =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${name}, ${address}`)}`;
