
NOW=$(date +%s)
NUM_MEMBERS=0
NUM_WA=0
NUM_MISMATCH=0
for code in `sqlite3 clubhouse.db "select code from members order by code;"`;
do



  NUM=$(sqlite3 testtcmembership.db "select count(*) from members where code = '${code}';")
  if (( $NUM > 1 )); then
    echo "Ignoring duplicate fob entry $code in membership"
    continue
  fi

  NUM=$(sqlite3 testwildapricot.db "select count(*) from members where code = '${code}';")
  if (( $NUM > 1 )); then
    echo "Ignoring duplicate fob entry $code in Wild Apricot DB!"
    continue
  fi

  DATE=$(sqlite3 testtcmembership.db "select expiration from members where code = '${code}';")
  ACTIVE=$(sqlite3 testtcmembership.db "select member_active from members where code = '${code}';")
  DATESECOND=$(date -d $DATE +%s)

  if [[ $DATESECOND -ge $NOW ]] && [[ $ACTIVE -gt 0 ]]; then
    TCACTIVE=True
    let NUM_MEMBERS++
  else
    TCACTIVE=False
  fi

  #echo $code-$TCACTIVE



  # wildapricot: member_enabled, member_status, expiration, code

  WADATE=$(sqlite3 testwildapricot.db "select expiration from members where code = '${code}';")
  WAENABLED=$(sqlite3 testwildapricot.db "select member_enabled from members where code = '${code}';")
  WASTATUS=$(sqlite3 testwildapricot.db "select member_status from members where code = '${code}';")
  WADATESECOND=$(date -d "$WADATE" +%s)

  if [[ $WADATESECOND -ge $NOW ]] && [[ $WAENABLED -gt 0 ]] && [[ $WASTATUS == "Active" ]]; then
    WAACTIVE=True
    let NUM_WA++
  else
    WAACTIVE=False
  fi

  #if [[ $WAACTIVE == "True" ]]; then

    #echo $code is active!
  #fi

  if [[ "$code-$WAACTIVE" != "$code-$TCACTIVE" ]]; then
    #echo mismatch on code $code, ch is $TCACTIVE, wa is $WAACTIVE
    let NUM_MISMATCH++
  fi
  #echo CODE: $code
done

echo Active Clubhouse:   $NUM_MEMBERS
echo Active WildApricot: $NUM_WA
echo Total Mismatch:     $NUM_MISMATCH
