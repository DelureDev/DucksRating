CHANNEL = "DUCKS_POKER"
CLUB_UTC_OFFSET_HOURS = 3  # Moscow time: post dates are stamped on the club's clock
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0.0.0 Safari/537.36")
FETCH_DELAY_SECONDS = 1.5
# The summer season froze with msg 469 (LAST CALL, 03.09, posted after
# midnight so dated 04.09); the autumn season — «Season 2» — starts right
# after it. A msg id, not a date, because of that past-midnight stamp.
SEASON_2_FIRST_MSG = 470
