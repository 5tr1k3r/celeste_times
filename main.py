import logging
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from dotenv import dotenv_values
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()


@dataclass
class AreaStats:
    name: str
    completed: bool
    time_played: int
    deaths: int


@dataclass
class SaveFile:
    id_: int
    game_completed: bool
    total_time: int
    total_deaths: int
    areas: list[AreaStats]


def parse_time(time_: int) -> str:
    ms = int(time_) // 10000
    hours, remainder = divmod(ms, 3600000)
    mins, remainder = divmod(remainder, 60000)
    secs, ms = divmod(remainder, 1000)

    time_components = []
    if hours > 0:
        time_components.append(f"{hours}:")
        time_components.append(f"{mins:02d}:")
    elif mins > 0:
        time_components.append(f"{mins}:")

    time_components.append(f"{secs:02d}." if hours > 0 or mins > 0 else f"{secs}.")
    time_components.append(f"{ms:03d}")

    return "".join(time_components)


def get_saves_path() -> Path:
    env_path = Path(".env")
    if env_path.exists():
        saves_path = dotenv_values(env_path)["SAVES_PATH"]
        logger.debug(f"Using Celeste saves path: {saves_path}")
    else:
        saves_path = input("Please enter the path to Celeste saves: ")
        env_path.write_text(f"SAVES_PATH={saves_path}")

    return Path(saves_path)


def load_all_saves(saves_path: Path, max_saves: int = 10) -> list[ET.ElementTree]:
    total_count = 0
    all_saves = []
    for i in range(max_saves):
        savefile_path = Path(saves_path) / f"{i}.celeste"
        if not savefile_path.exists():
            break

        total_count += 1
        all_saves.append(ET.parse(savefile_path))

    logger.debug(f"Found {total_count} save files")
    return all_saves


def show_overview(all_saves: list[ET.ElementTree]):
    for i, save in enumerate(all_saves):
        print(f"ID: {i}")
        for child in save.getroot():
            if child.tag == "Name":
                print(f"Name: {child.text}")
            elif child.tag == "Time":
                print(f"Time: {parse_time(int(child.text))}")
            elif child.tag == "TotalDeaths":
                print(f"Deaths: {child.text}")
        print()


def ask_to_compare() -> tuple[int, int]:
    save_a, save_b = input("Please select two savefile IDs to compare (example: `0 4`): ").split()
    return int(save_a), int(save_b)


def parse_areas(all_saves: list[ET.ElementTree], save_id: int) -> SaveFile:
    area_names = list(reversed(["Prologue", None, None,
                                "1a", "1b", "1c",
                                "2a", "2b", "2c",
                                "3a", "3b", "3c",
                                "4a", "4b", "4c",
                                "5a", "5b", "5c",
                                "6a", "6b", "6c",
                                "7a", "7b", "7c",
                                None, None, None,
                                "8a", "8b", "8c",
                                "Farewell", None, None]))
    total_deaths = 0
    total_time = 0
    areas = []
    game_completed = False

    for child in all_saves[save_id].getroot():
        if child.tag == "Areas":
            for area in child:
                for area_stats in area[0]:
                    area_name = area_names.pop()
                    if area_name is None:
                        continue

                    completed = area_stats.attrib["Completed"] == "true"
                    time_played = int(area_stats.attrib["TimePlayed"])
                    deaths = int(area_stats.attrib["Deaths"])

                    if completed:
                        if area_name == "Farewell":
                            game_completed = True

                    areas.append(AreaStats(area_name, completed, time_played, deaths))
                    total_time += time_played
                    total_deaths += deaths
            break

    return SaveFile(save_id, game_completed, total_time, total_deaths, areas)


def find_diff(time_a: int, time_b: int) -> str:
    a_is_faster = time_a < time_b
    diff = max(time_a, time_b) - min(time_a, time_b)
    return f"{'-' * a_is_faster}{parse_time(diff)}"


def generate_results(save_a: SaveFile, save_b: SaveFile):
    # Load the template
    file_loader = FileSystemLoader(".")
    env = Environment(loader=file_loader)
    template = env.get_template("template.html")

    time_rows = []
    death_rows = []
    for area_a, area_b in zip(save_a.areas, save_b.areas):
        if not (area_a.completed and area_b.completed):
            continue

        time_rows.append({
            "chapter": area_a.name,
            "result_a": parse_time(area_a.time_played),
            "result_b": parse_time(area_b.time_played),
            "diff": find_diff(area_a.time_played, area_b.time_played),
            "a_is_better": area_a.time_played < area_b.time_played,
            "b_is_better": area_a.time_played > area_b.time_played,
        })

        death_rows.append({
            "chapter": area_a.name,
            "result_a": area_a.deaths,
            "result_b": area_b.deaths,
            "diff": area_a.deaths - area_b.deaths,
            "a_is_better": area_a.deaths < area_b.deaths,
            "b_is_better": area_a.deaths > area_b.deaths,
        })

    result_a = None if save_a.game_completed else "-"
    result_b = None if save_b.game_completed else "-"
    diff = None if save_a.game_completed and save_b.game_completed else "-"

    time_rows.append({
        "chapter": "TOTAL TIME",
        "result_a": result_a or parse_time(save_a.total_time),
        "result_b": result_b or parse_time(save_b.total_time),
        "diff": diff or find_diff(save_a.total_time, save_b.total_time),
        "a_is_better": False if diff else save_a.total_time < save_b.total_time,
        "b_is_better": False if diff else save_a.total_time > save_b.total_time,
    })

    death_rows.append({
        "chapter": "TOTAL DEATHS",
        "result_a": result_a or save_a.total_deaths,
        "result_b": result_b or save_b.total_deaths,
        "diff": diff or (save_a.total_deaths - save_b.total_deaths),
        "a_is_better": False if diff else save_a.total_deaths < save_b.total_deaths,
        "b_is_better": False if diff else save_a.total_deaths > save_b.total_deaths,
    })

    # Data to populate the template
    data = {
        "title": "Celeste Savefile Comparison",
        "heading": f"Comparing Celeste all chapters runs, {save_a.id_} vs. {save_b.id_}",
        "time_rows": time_rows,
        "death_rows": death_rows,
        "save_id_a": save_a.id_,
        "save_id_b": save_b.id_,
    }

    # Render the template with the data
    output = template.render(data)

    # Write the rendered HTML to a file
    html_path = Path(f"./results/{save_a.id_}_vs_{save_b.id_}.html")
    with open(html_path, "w") as html_file:
        html_file.write(output)

    webbrowser.open(str(html_path.absolute()))


def run():
    saves_path = get_saves_path()
    all_saves = load_all_saves(saves_path)
    show_overview(all_saves)
    save_id_a, save_id_b = ask_to_compare()
    save_a = parse_areas(all_saves, save_id_a)
    save_b = parse_areas(all_saves, save_id_b)
    generate_results(save_a, save_b)


if __name__ == "__main__":
    run()
