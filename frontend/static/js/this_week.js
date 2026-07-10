const WeekEls = {
	title: document.querySelector('#week-title'),
	source: document.querySelector('#week-source'),
	loading: document.querySelector('#week-loading'),
	grid: document.querySelector('#week-grid'),
	dialog: document.querySelector('#match-dialog'),
	results: document.querySelector('#match-results'),
	context: document.querySelector('#match-context'),
	filter: document.querySelector('#match-filter'),
	empty: document.querySelector('#match-empty'),
	searchAll: document.querySelector('#match-search-all'),
	close: document.querySelector('#close-matches'),
	add: {
		form: document.querySelector('#add-form'),
		title: document.querySelector('#add-window h2'),
		cover: document.querySelector('#add-cover'),
		comicvineId: document.querySelector('#comicvine-input'),
		rootFolder: document.querySelector('#rootfolder-input'),
		volumeFolder: document.querySelector('#volumefolder-input'),
		monitorVolume: document.querySelector('#monitor-volume-input'),
		monitorIssues: document.querySelector('#monitor-issues-input'),
		monitoringScheme: document.querySelector('#monitoring-scheme-input'),
		specialVersion: document.querySelector('#specialoverride-input'),
		autoSearch: document.querySelector('#auto-search-input'),
		submit: document.querySelector('#add-volume')
	}
};

let activeComic = null;
let activeApiKey = null;
let activeVolume = null;
let suggestedVolumeFolder = '';

function openAddVolume(volume, apiKey) {
	activeVolume = volume;
	WeekEls.add.submit.innerText = 'Add Volume';
	WeekEls.add.submit.disabled = true;
	WeekEls.add.title.innerText = `${volume.title}${volume.year ? ` (${volume.year})` : ''}`;
	WeekEls.add.cover.src = volume.cover_link;
	WeekEls.add.comicvineId.value = volume.comicvine_id;
	WeekEls.add.specialVersion.value = 'auto';
	const preferences = getLocalStorage(
		'monitor_new_volume', 'monitor_new_issues', 'monitoring_scheme'
	);
	WeekEls.add.monitorVolume.value = preferences.monitor_new_volume;
	WeekEls.add.monitorIssues.value = preferences.monitor_new_issues;
	WeekEls.add.monitoringScheme.value = preferences.monitoring_scheme;
	WeekEls.add.volumeFolder.value = 'Loading suggested folder…';
	showWindow('add-window');

	sendAPI('POST', '/volumes/search', apiKey, {}, {
		comicvine_id: volume.comicvine_id,
		title: volume.title,
		year: volume.year,
		volume_number: volume.volume_number,
		publisher: volume.publisher
	}).then(response => response.json()).then(json => {
		suggestedVolumeFolder = json.result.folder;
		WeekEls.add.volumeFolder.value = suggestedVolumeFolder;
		WeekEls.add.submit.disabled = false;
	}).catch(() => {
		WeekEls.add.submit.innerText = 'Unable to prepare volume';
	});
}

function addWeeklyVolume() {
	if (!activeVolume) return;
	showLoadWindow('add-window');
	const folder = WeekEls.add.volumeFolder.value;
	const data = {
		comicvine_id: Number(WeekEls.add.comicvineId.value),
		root_folder_id: Number(WeekEls.add.rootFolder.value),
		monitor: WeekEls.add.monitorVolume.value === 'true',
		monitoring_scheme: WeekEls.add.monitoringScheme.value,
		monitor_new_issues: WeekEls.add.monitorIssues.value === 'true',
		volume_folder: folder !== suggestedVolumeFolder ? folder : '',
		special_version: WeekEls.add.specialVersion.value || null,
		auto_search: WeekEls.add.autoSearch.checked,
		metron_series_id: activeVolume.metron_series_id || null
	};
	setLocalStorage({
		monitor_new_volume: data.monitor,
		monitor_new_issues: data.monitor_new_issues,
		monitoring_scheme: data.monitoring_scheme
	});
	sendAPI('POST', '/volumes', activeApiKey, {}, data)
		.then(response => response.json())
		.then(() => window.location.reload())
		.catch(error => {
			WeekEls.add.submit.innerText = error.status === 509 ?
				'ComicVine API rate limit reached' : 'Unable to add volume';
			WeekEls.add.submit.disabled = false;
			showWindow('add-window');
		});
}

function loadRootFolders(apiKey) {
	fetchAPI('/rootfolder', apiKey).then(json => {
		WeekEls.add.rootFolder.innerHTML = '';
		json.result.forEach(folder => {
			const option = document.createElement('option');
			option.value = folder.id;
			option.innerText = folder.folder;
			WeekEls.add.rootFolder.appendChild(option);
		});
	});
}

function candidateStatus(volume, comic) {
	if (volume.issue_store_date) {
		const distance = volume.release_distance_days;
		return `Issue #${comic.issue_number} · In store ${volume.issue_store_date}` +
			(distance === 0 ? ' · Same day' : ` · ${distance} day${distance === 1 ? '' : 's'} away`);
	}
	if (volume.issue_found) return `Issue #${comic.issue_number} has no in-store date`;
	return `Issue #${comic.issue_number} not found in this series`;
}

function chooseMatch(volume) {
	const buttons = WeekEls.results.querySelectorAll('button');
	buttons.forEach(button => button.disabled = true);
	sendAPI('PUT', '/weekly-releases', activeApiKey, {}, {
		comic_url: activeComic.url,
		comicvine_id: volume.comicvine_id
	}).then(() => {
		WeekEls.dialog.classList.add('hidden');
		if (volume.already_added) {
			window.location.href = `${url_base}/volumes/${volume.already_added}`;
		} else {
			openAddVolume(volume, activeApiKey);
		}
	}).catch(() => {
		buttons.forEach(button => button.disabled = false);
	});
}

function renderMatches(filter = '') {
	const normalized = filter.trim().toLowerCase();
	const matches = (activeComic?.matches || []).filter(volume =>
		`${volume.title} ${volume.year || ''} ${volume.publisher || ''}`
			.toLowerCase().includes(normalized)
	);
	WeekEls.results.innerHTML = '';
	WeekEls.empty.innerText = activeComic?.matches?.length ?
		'No candidates match this filter.' :
		'ComicVine returned no candidate series for this title.';
	WeekEls.empty.classList.toggle('hidden', matches.length !== 0);
	matches.forEach(volume => {
		const button = document.createElement('button');
		button.type = 'button';
		button.className = 'match-card';
		const cover = document.createElement('img');
		cover.src = volume.cover_link;
		cover.onerror = () => {
			cover.onerror = null;
			cover.src = `${url_base}/static/img/favicon.svg`;
		};
		const body = document.createElement('span');
		body.className = 'match-card-body';
		const title = document.createElement('strong');
		title.innerText = `${volume.title}${volume.year ? ` (${volume.year})` : ''}`;
		const publisher = document.createElement('small');
		publisher.innerText = volume.publisher || 'Unknown publisher';
		const validation = document.createElement('small');
		validation.className = volume.release_distance_days <= 7 &&
			volume.release_distance_days !== null ? 'match-valid' : 'match-warning';
		validation.innerText = candidateStatus(volume, activeComic);
		const action = document.createElement('span');
		action.className = 'match-action';
		action.innerText = volume.already_added ? 'Use library volume' : 'Select series';
		body.append(title, publisher, validation, action);
		button.append(cover, body);
		button.onclick = () => chooseMatch(volume);
		WeekEls.results.appendChild(button);
	});
}

function showMatches(comic, apiKey) {
	activeComic = comic;
	activeApiKey = apiKey;
	WeekEls.context.innerHTML = '';
	const title = document.createElement('strong');
	title.innerText = comic.title;
	const date = document.createElement('span');
	date.innerText = `Weekly pack: ${comic.pack_date || 'current week'}`;
	WeekEls.context.append(title, date);
	WeekEls.filter.value = '';
	WeekEls.dialog.classList.remove('hidden');
	renderMatches();
	WeekEls.filter.focus();
}

function openComic(comic, apiKey) {
	const match = comic.selected_match;
	if (!match) {
		showMatches(comic, apiKey);
		return;
	}
	if (comic.library_volume_id) {
		window.location.href = `${url_base}/volumes/${comic.library_volume_id}`;
		return;
	}
	openAddVolume(match, apiKey);
}

function downloadWeeklyIssue(event, comic, apiKey) {
	event.stopPropagation();
	const button = event.currentTarget;
	button.disabled = true;
	const icon = button.querySelector('img');
	icon.src = `${url_base}/static/img/loading.svg`;
	icon.classList.add('spinning');
	button.title = `Queueing ${comic.title}`;
	sendAPI('POST', '/system/tasks', apiKey, {}, {
		cmd: 'auto_search_issue',
		volume_id: comic.library_volume_id,
		issue_id: comic.library_issue_id
	}).then(() => {
		button.title = `Auto search queued for ${comic.title}`;
	}).catch(() => {
		button.disabled = false;
		icon.src = `${url_base}/static/img/download.svg`;
		icon.classList.remove('spinning');
		button.title = `Unable to queue ${comic.title}`;
	});
}

usingApiKey().then(apiKey => {
	activeApiKey = apiKey;
	loadRootFolders(apiKey);
	fetchAPI('/weekly-releases', apiKey).then(json => {
		WeekEls.title.innerText = json.result.title;
		WeekEls.source.href = json.result.source_url;
		WeekEls.grid.innerHTML = '';
		json.result.comics.forEach(comic => {
			comic.pack_date = json.result.pack_date;
			const button = document.createElement('article');
			button.className = 'week-card';
			button.tabIndex = 0;
			button.setAttribute('role', 'button');
			const coverArea = document.createElement('div');
			coverArea.className = 'week-cover';
			const image = document.createElement('img');
			image.src = comic.cover || `${url_base}/static/img/favicon.svg`;
			image.onerror = () => {
				image.onerror = null;
				image.src = `${url_base}/static/img/favicon.svg`;
			};
			image.alt = '';
			coverArea.appendChild(image);
			if (comic.is_monitored && comic.library_issue_id) {
				const download = document.createElement('button');
				download.type = 'button';
				download.className = 'week-download';
				download.title = `Search and download ${comic.title}`;
				download.setAttribute('aria-label', download.title);
				const downloadIcon = document.createElement('img');
				downloadIcon.src = `${url_base}/static/img/download.svg`;
				downloadIcon.alt = '';
				download.appendChild(downloadIcon);
				download.onclick = event => downloadWeeklyIssue(event, comic, apiKey);
				coverArea.appendChild(download);
			}
			const title = document.createElement('strong');
			title.innerText = comic.title;
			const matchNote = document.createElement('small');
			matchNote.className = 'week-match-note';
			if (comic.selected_match?.match_source === 'Metron') {
				matchNote.classList.add('metron-match');
				matchNote.innerText = 'Matched via Metron';
			} else if (!comic.selected_match && comic.metron_match_found) {
				matchNote.classList.add('no-match');
				matchNote.innerText = 'Found in Metron, but no ComicVine link';
			} else if (!comic.selected_match && comic.metron_checked) {
				matchNote.classList.add('no-match');
				matchNote.innerText = 'Not found in ComicVine or Metron';
			}
			const status = document.createElement('span');
			status.className = `week-status ${comic.status}`;
			status.title = comic.status === 'downloaded' ? 'Downloaded' :
				comic.status === 'missing' ? 'Monitored but missing' : 'Not monitored';
			button.append(coverArea, status, title);
			if (matchNote.innerText) button.appendChild(matchNote);
			button.onclick = () => openComic(comic, apiKey);
			button.onkeydown = event => {
				if (event.target !== button) return;
				if (event.key === 'Enter' || event.key === ' ') {
					event.preventDefault();
					openComic(comic, apiKey);
				}
			};
			WeekEls.grid.appendChild(button);
		});
		WeekEls.loading.classList.add('hidden');
		WeekEls.grid.classList.remove('hidden');
	}).catch(() => {
		WeekEls.loading.innerHTML =
			'<div><strong>Weekly comics could not be loaded.</strong><small>Check the task log for the GetComics or ComicVine error.</small></div>';
	});
});

WeekEls.close.onclick = () => WeekEls.dialog.classList.add('hidden');
WeekEls.add.form.action = 'javascript:addWeeklyVolume();';
WeekEls.filter.oninput = () => renderMatches(WeekEls.filter.value);
WeekEls.searchAll.onclick = () => {
	window.location.href = `${url_base}/add?q=${encodeURIComponent(activeComic.query)}`;
};
WeekEls.dialog.onclick = event => {
	if (event.target === WeekEls.dialog) WeekEls.dialog.classList.add('hidden');
};
document.addEventListener('keydown', event => {
	if (event.key === 'Escape') WeekEls.dialog.classList.add('hidden');
});
