# -*- coding: utf-8 -*-
"""Tests for Habito module."""

from datetime import datetime, date, timedelta
from unittest import TestCase
from unittest.mock import patch
from click.testing import CliRunner

from habito import habito, models
from tests import HabitoTestCase


class HabitoTests(HabitoTestCase):
    """Test scenarios for Habito commands."""

    # Scenarios
    # Add: uber goal, daily commitment, automatically add weekly checkpoints
    # Statistics: don't break the chain
    # Suggestions: off track, time to increase difficulty, remind the why!

    # flake8: noqa
    def setUp(self):
        self.runner = CliRunner()
        habito.database_name = ":memory:"
        models.setup(habito.database_name)

    def tearDown(self):
        models.db.drop_tables([models.Habit, models.Activity, models.Summary],
                              safe=True)

    def test_habito_cli_sets_up_default_commandset(self):
        result = habito.cli

        commands = {'list': habito.list,
                    'add': habito.add,
                    'checkin': habito.checkin,
                    'edit': habito.edit,
                    'delete': habito.delete}

        assert result.commands == commands

    @patch("habito.habito.click.get_app_dir")
    @patch("habito.habito.mkdir")
    @patch("habito.habito.models.setup")
    def test_habito_cli_sets_up_database(self, models_setup, mkdir, click):
        result = self._run_command(habito.cli, ["add"])

        assert models_setup.called

    @patch("habito.habito.click.get_app_dir")
    @patch("habito.habito.mkdir")
    def test_habito_cli_sets_up_app_directory(self, mkdir_mock, click_mock):
        with patch("habito.habito.path.exists") as path_exists:
            path_exists.return_value = False
            result = self._run_command(habito.cli, ["add"])

            assert click_mock.called
            assert mkdir_mock.called
   
    def test_habito_list_table_adapts_to_terminal_width(self):
        for terminal_width in range(0, 101, 5):
            nr_of_dates = terminal_width//10 - 4
            habito.TERMINAL_WIDTH = terminal_width 
            result = self._run_command(habito.list, ["-l"])
            if nr_of_dates < 1:
                assert "terminal window is too small" in result.output
                assert result.exit_code == 1
            else:
                assert result.exit_code == 0
                for i in range(nr_of_dates):
                    date_string = "{dt.month}/{dt.day}".format(dt=(datetime.now() - timedelta(days=i)))
                    assert date_string in result.output
        habito.TERMINAL_WIDTH = 80

    def test_habito_list_lists_off_track_habits(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, ["Habit", "-q -9.1"])

        result = self._run_command(habito.list, ["-l"])

        # Habit is off track with quanta <= goal. Verify 'x'
        assert habit.name in result.output
        assert u"-9.1" in result.output

    def test_habito_list_lists_on_track_habits(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, ["Habit", "-q 9.1"])

        result = self._run_command(habito.list, ["-l"])

        # Habit is on track with quanta >= goal. Verify 'tick'
        assert habit.name in result.output
        assert u"9.1" in result.output

    def test_habito_list_skips_inactive_habits(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, ["Habit", "-q 9.1"])
        habit.active = False
        habit.save()

        result = self._run_command(habito.list, ["-l"])

        # Habit is on track with quanta >= goal. Verify 'tick'
        assert habit.name not in result.output
        assert u"9.1" not in result.output

    def test_habito_list_should_show_streak(self):
        habit = self.create_habit()
        self.add_summary(habit, streak=10)

        result = self._run_command(habito.list)

        assert "10 days" in result.output

    def test_habito_add_should_add_a_habit(self):
        result = self._run_command(habito.add,
                ["dummy habit", "10.01"])

        assert models.Habit.get().name == "dummy habit"
        assert models.Summary.get().streak == 0

    def test_habito_checkin_should_show_error_if_no_habit_exists(self):
        result = self._run_command(habito.checkin,
                ["dummy habit", "-q 9.1"])

        assert result.exit_code == 0
        assert result.output.startswith("No habit matched the")

    def test_habito_checkin_should_show_error_if_name_is_empty(self):
        result = self._run_command(habito.checkin)

        assert result.exit_code == 0
        assert result.output.startswith("No habit specified")

    def test_habito_checkin_should_show_error_if_multiple_habits_match(self):
        dummy_date = date(1201, 10, 12)
        habit = self.create_habit()
        habit_two = self.create_habit(name="Habit Two",
                                      created_date=dummy_date,
                                      quantum=0,
                                      magica="be awesome!")

        result = self._run_command(habito.checkin,
                                   ["Habit", "-q 9.1"])

        assert result.exit_code == 0
        assert result.output.startswith("More than one habits matched the")

    def test_habito_checkin_should_add_data_for_a_habit(self):
        habit = self.create_habit()
        self.add_summary(habit)
        result_units = "9.1 dummy_units"

        result = self._run_command(habito.checkin,
                                   ["Habit", "-q 9.1"])
        activity_entry = models.Activity\
            .get(models.Activity.for_habit == habit)

        assert result.output.find(result_units) != -1
        assert result.output.find(habit.name) != -1
        assert activity_entry.quantum == 9.1

    def test_habito_checkin_should_skip_inactive_habit(self):
        habit = self.create_habit(active=False)
        self.add_summary(habit)
        result_units = "9.1 dummy_units"

        result = self._run_command(habito.checkin,
                                   ["Habit", "-q 9.1"])

        activity_entry = models.Activity\
            .select().where(models.Activity.for_habit == habit)
        assert result.output.find(result_units) == -1
        assert result.output.find(habit.name) == -1
        assert activity_entry.count() == 0

    def test_habito_checkin_should_update_past_date(self):
        habit = self.create_habit()
        self.add_summary(habit)
        for i in range(5):
            d = datetime.now() - timedelta(days=i)
            date_str = "{d.month}/{d.day}".format(d=d).strip()
            checkin_result = self._run_command(habito.checkin, ["Habit", "-d {}".format(date_str), "-q 35.0"])

            self._verify_checkin_date(date_str, d.year, checkin_result.output)
            assert "35.0 dummy_units" in checkin_result.output
        list_result = self._run_command(habito.list, ["-l"])
        assert list_result.output.count("35") > 3

    def test_habito_checkin_should_update_past_year(self):
        habit = self.create_habit()
        self.add_summary(habit)
        d = datetime.now() + timedelta(days=2)
        date_str = "{d.month}/{d.day}".format(d=d).strip()

        checkin_result = self._run_command(habito.checkin, ["Habit", "-d {}".format(date_str), "-q 35.0"])

        a = models.Activity.select()\
            .where(models.Activity.update_date.year == d.year-1).get()
        assert a.quantum == 35.0
        self._verify_checkin_date(date_str, d.year-1, checkin_result.output)
        assert "35.0 dummy_units" in checkin_result.output

    def test_habito_checkin_can_add_multiple_data_points_on_same_day(self):
        habit = self.create_habit()
        self.add_summary(habit)
        result_units_one = "9.1 dummy_units"
        result_units_two = "10.0001 dummy_units"

        self._run_command(habito.checkin, ["Habit", "-q 9.1"])
        result = self._run_command(habito.checkin, ["Habit", "-q 10.0001"])

        activity_entry = models.Activity\
            .select().where(models.Activity.for_habit == habit)

        assert result.output.find(result_units_two) != -1
        assert result.output.find(habit.name) != -1
        assert activity_entry.count() == 2
        assert activity_entry[0].quantum == 9.1
        assert activity_entry[1].quantum == 10.0001

    def test_habito_checkin_asks_user_input_if_quantum_is_not_provided(self):
        habit = self.create_habit()
        self.add_summary(habit)
        result_units_one = "9.1 dummy_units"

        # Pass \n to stdin to ensure prompt continues to appear until
        # a value is provided
        result = self._run_command_with_stdin(habito.checkin, ["Habit"], "\n9.1")

        assert result.exit_code == 0
        assert result.output.find(result_units_one) != -1

    def test_habito_checkin_increments_streak_for_a_habit(self):
        habit = self.create_habit()
        self.add_activity(habit, update_date=HabitoTests.one_day_ago)
        self.add_activity(habit, update_date=HabitoTests.two_days_ago)
        self.add_summary(habit, streak=2)

        self._run_command(habito.checkin, ["Habit", "-q 9.1"])

        assert models.Summary.get().streak == 3

    def test_habito_checkin_review_mode_iterates_all_habits(self):
        habit_one = self.create_habit()
        habit_two = self.create_habit(name="HabitTwo", quantum=2)
        habit_three = self.create_habit(name="HabitThree", active=False, quantum=2)
        self.add_summary(habit_one)
        self.add_summary(habit_two)
        self.add_summary(habit_three)

        result = self._run_command_with_stdin(habito.checkin, ["--review"], "1.0\n2.0")

        activities = list(models.Activity.select())
        assert result.exit_code == 0
        assert len(activities) == 2
        assert activities[0].quantum == 1.0
        assert activities[1].quantum == 2.0

    def test_habito_checkin_review_mode_doesnt_update_default(self):
        habit = self.create_habit()
        self.add_summary(habit)

        result = self._run_command_with_stdin(habito.checkin, ["-r"], "\n")

        assert result.exit_code == 0
        assert models.Activity.select().count() == 0

    def test_edit(self):
        habit = self.create_habit()
        self.add_summary(habit)

        edit_result = self._run_command(habito.edit, [str(habit.id), "-n EHabit"])

        assert edit_result.output == ("Habit with id 1 has been saved with"
                                      " name: EHabit and quantum: 0.0.\n")
        list_result = self._run_command(habito.list)
        assert "EHabit" in list_result.output
        assert habit.name not in list_result.output

    def test_non_existing_edit(self):
        edit_result = self._run_command(habito.edit, [str(10), "-n test"])

        assert edit_result.output == "The habit you're trying to edit does not exist!\n"
        assert edit_result.exit_code == 1

    def test_delete_removes_habit_activity(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, [habit.name, "-q 3"])

        delete_result = self._run_command_with_stdin(habito.delete, ["1"], "y")

        msg = "Are you sure you want to delete habit 1: {} (this cannot be"\
              " undone!)".format(habit.name)
        assert msg in delete_result.output
        assert "{0}: {1} has been deleted!".format(habit.id, habit.name) in delete_result.output
        assert habito.models.Habit.select().count() == 0

    def test_delete_should_not_delete_for_no_confirm(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, [habit.name, "-q 3"])

        delete_result = self._run_command_with_stdin(habito.delete, ["1"], "n")

        msg = "Are you sure you want to delete habit 1: {} (this cannot be"\
              " undone!)".format(habit.name)
        assert msg in delete_result.output
        assert habito.models.Habit.select().count() == 1

    def test_non_existing_delete(self):
        delete_result = self._run_command(habito.delete, ["20"])

        assert "The habit you want to remove does not seem to exist!" in delete_result.output

    def test_delete_with_keep_logs_marks_habit_inactive(self):
        habit = self.create_habit()
        self.add_summary(habit)
        self._run_command(habito.checkin, [habit.name, "-q 3"])

        delete_result = self._run_command_with_stdin(habito.delete, ["1", "--keeplogs"], "y")

        assert habito.models.Activity.select().count() == 1
        assert habito.models.Habit.select().where(habito.models.Habit.active).count() == 0
    
    def _verify_checkin_date(self, date_str, year, output):
        date = datetime.strptime(date_str, "%m/%d")\
            .replace(year=year).strftime("%a %b %d %Y")
        assert date in output

    def _run_command(self, command, args=[]):
        return self._run_command_with_stdin(command, args, stdin=None)

    def _run_command_with_stdin(self, command, args, stdin):
        result = self.runner.invoke(command, args=args, input=stdin)

        print(result.output)
        print(result.exc_info)

        return result
