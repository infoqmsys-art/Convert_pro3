function fetchData() {
    fetch('/cat/simplemon.py')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const container = document.querySelector('.widget-container');
            container.innerHTML = ''; // 기존 내용을 비움

            data.forEach(item => {
                const widget = `
                    <div class="widget">
                        <div class="widget-title">
                            ${item.title}
                            <span class="status-indicator" style="background-color: ${item.indicator_color};"></span>
                        </div>
                        <div><b>ID: ${item.device_id}</b></div>
                        <div>${item.timestamp}</div>
                        <div>Battery: <span style="color:${item.battery_color}">${item.battery_level}%</span></div>
                        <div>Temp: ${item.temp_display}</div>
                        <div>Humidity: ${item.humidity}%</div>
                    </div>
                `;
                container.insertAdjacentHTML('beforeend', widget);
            });
        })
        .catch(error => {
            const errorDisplay = document.getElementById('errorDisplay');
            errorDisplay.textContent = `데이터를 가져오는 중 오류 발생: ${error.message}`;
            console.error('Error fetching data:', error);
        });
}

// 데이터 갱신 주기 설정
setInterval(fetchData, 5000);
fetchData(); // 페이지 로드 시 초기 데이터 가져오기
