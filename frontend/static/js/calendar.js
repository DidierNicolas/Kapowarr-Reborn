const CalendarEls = {
	grid: document.querySelector('#calendar'),
	title: document.querySelector('#calendar-title'),
	previous: document.querySelector('#previous-month'),
	next: document.querySelector('#next-month'),
	today: document.querySelector('#today'),
	dialog: document.querySelector('#calendar-day-dialog'),
	dayTitle: document.querySelector('#calendar-day-title'),
	dayIssues: document.querySelector('#calendar-day-issues'),
	dayClose: document.querySelector('#calendar-day-close'),
	icalFeed: document.querySelector('#ical-feed')
};

let displayedMonth = new Date();
displayedMonth = new Date(displayedMonth.getFullYear(), displayedMonth.getMonth(), 1);

function localDateString(date) {
	const year = date.getFullYear();
	const month = String(date.getMonth() + 1).padStart(2, '0');
	const day = String(date.getDate()).padStart(2, '0');
	return `${year}-${month}-${day}`;
}

function buildIssueEntry(issue, dateString, today) {
	const entry = document.createElement('a');
	entry.href = `${url_base}/volumes/${issue.volume_id}`;
	if (issue.tentative) entry.classList.add('tentative');
	if (issue.downloaded) {
		entry.classList.add(issue.monitored ? 'downloaded-monitored' : 'downloaded-unmonitored');
	} else if (dateString >= today) {
		entry.classList.add('unreleased');
	} else {
		entry.classList.add(issue.monitored ? 'missing-monitored' : 'missing-unmonitored');
	}

	const name = document.createElement('strong');
	name.innerText = issue.volume_title;
	const details = document.createElement('span');
	details.innerText = `Issue #${issue.issue_number}${issue.title ? ` · ${issue.title}` : ''}${issue.source ? ` · ${issue.source}` : ''}`;
	entry.append(name, details);
	entry.title = `${issue.volume_title} #${issue.issue_number}${issue.tentative ? ` · Tentative ${issue.source} date` : ''}`;
	return entry;
}

function showDay(date, issues, today) {
	const dateString = localDateString(date);
	CalendarEls.dayTitle.innerText = date.toLocaleDateString(undefined, {
		weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
	});
	CalendarEls.dayIssues.innerHTML = '';
	issues.forEach(issue => CalendarEls.dayIssues.appendChild(
		buildIssueEntry(issue, dateString, today)
	));
	CalendarEls.dialog.showModal();
}

function renderCalendar(issues) {
	CalendarEls.grid.innerHTML = '';
	CalendarEls.title.innerText = displayedMonth.toLocaleDateString(undefined, {
		month: 'long', year: 'numeric'
	});

	for (const weekday of ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']) {
		const heading = document.createElement('div');
		heading.className = 'weekday';
		heading.innerText = weekday;
		CalendarEls.grid.appendChild(heading);
	}

	const today = localDateString(new Date());
	const issuesByDate = issues.reduce((groups, issue) => {
		(groups[issue.date] ||= []).push(issue);
		return groups;
	}, {});

	const gridStart = new Date(displayedMonth);
	gridStart.setDate(1 - displayedMonth.getDay());

	for (let index = 0; index < 42; index++) {
		const date = new Date(gridStart);
		date.setDate(gridStart.getDate() + index);
		const dateString = localDateString(date);
		const cell = document.createElement('div');
		cell.className = 'calendar-day';
		if (date.getMonth() !== displayedMonth.getMonth()) cell.classList.add('outside-month');
		if (dateString === today) cell.classList.add('today');

		const number = document.createElement('time');
		number.dateTime = dateString;
		number.innerText = date.getDate();
		cell.appendChild(number);

		const dayIssues = issuesByDate[dateString] || [];
		if (dayIssues.length > 2) cell.classList.add('has-overflow');
		dayIssues.slice(0, 2).forEach(issue => cell.appendChild(
			buildIssueEntry(issue, dateString, today)
		));
		if (dayIssues.length > 2) {
			const more = document.createElement('button');
			more.type = 'button';
			more.className = 'calendar-more';
			more.innerText = `+${dayIssues.length - 2} more`;
			more.setAttribute('aria-label', `Show all ${dayIssues.length} issues on ${dateString}`);
			more.onclick = () => showDay(date, dayIssues, today);
			cell.appendChild(more);
		}

		CalendarEls.grid.appendChild(cell);
	}
}

function loadCalendar(apiKey) {
	const month = localDateString(displayedMonth).slice(0, 7);
	fetchAPI('/calendar', apiKey, {month: month})
		.then(json => renderCalendar(json.result));
}

function changeMonth(apiKey, amount) {
	displayedMonth = new Date(
		displayedMonth.getFullYear(), displayedMonth.getMonth() + amount, 1
	);
	loadCalendar(apiKey);
}

usingApiKey().then(apiKey => {
	loadCalendar(apiKey);
	CalendarEls.previous.onclick = () => changeMonth(apiKey, -1);
	CalendarEls.next.onclick = () => changeMonth(apiKey, 1);
	CalendarEls.today.onclick = () => {
		const now = new Date();
		displayedMonth = new Date(now.getFullYear(), now.getMonth(), 1);
		loadCalendar(apiKey);
	};
	CalendarEls.icalFeed.onclick = async () => {
		const feedUrl = `${window.location.origin}${url_base}/api/calendar.ics?api_key=${encodeURIComponent(apiKey)}`;
		try {
			await navigator.clipboard.writeText(feedUrl);
			CalendarEls.icalFeed.innerText = 'iCal Feed Copied';
			setTimeout(() => CalendarEls.icalFeed.innerText = 'Copy iCal Feed', 1800);
		} catch (error) {
			window.prompt('Copy this iCalendar subscription URL:', feedUrl);
		}
	};
});

CalendarEls.dayClose.onclick = () => CalendarEls.dialog.close();
CalendarEls.dialog.onclick = event => {
	if (event.target === CalendarEls.dialog) CalendarEls.dialog.close();
};
