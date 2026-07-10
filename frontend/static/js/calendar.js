const CalendarEls = {
	grid: document.querySelector('#calendar'),
	title: document.querySelector('#calendar-title'),
	previous: document.querySelector('#previous-month'),
	next: document.querySelector('#next-month'),
	today: document.querySelector('#today')
};

let displayedMonth = new Date();
displayedMonth = new Date(displayedMonth.getFullYear(), displayedMonth.getMonth(), 1);

function localDateString(date) {
	const year = date.getFullYear();
	const month = String(date.getMonth() + 1).padStart(2, '0');
	const day = String(date.getDate()).padStart(2, '0');
	return `${year}-${month}-${day}`;
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

		for (const issue of issuesByDate[dateString] || []) {
			const entry = document.createElement('a');
			entry.href = `${url_base}/volumes/${issue.volume_id}`;
			if (issue.tentative) entry.classList.add('tentative');
			if (issue.downloaded) {
				entry.className = issue.monitored ? 'downloaded-monitored' : 'downloaded-unmonitored';
			} else if (dateString >= today) {
				entry.className = 'unreleased';
			} else {
				entry.className = issue.monitored ? 'missing-monitored' : 'missing-unmonitored';
			}

			const name = document.createElement('strong');
			name.innerText = issue.volume_title;
			const details = document.createElement('span');
			details.innerText = `Issue #${issue.issue_number}${issue.title ? ` · ${issue.title}` : ''}${issue.source ? ` · ${issue.source}` : ''}`;
			entry.append(name, details);
			entry.title = `${issue.volume_title} #${issue.issue_number}${issue.tentative ? ` · Tentative ${issue.source} date` : ''}`;
			cell.appendChild(entry);
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
});
